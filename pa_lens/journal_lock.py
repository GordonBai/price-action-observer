"""Inode-keyed, owner-private locks compatible with Darwin SQLite WAL.

Never unlink sidecars: doing so could create two live lock domains.
"""
import fcntl
import os
from pathlib import Path
import stat
import sys


class JournalLock:
    def __init__(self, database, directory=None):
        self.fd = self.db_fd = None
        self.path = None
        try:
            database = Path(database).expanduser().resolve()
            self.db_fd = os.open(database, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            db = os.fstat(self.db_fd)
            if not stat.S_ISREG(db.st_mode) or db.st_uid != os.getuid():
                raise RuntimeError('journal must be an owned regular file')
            self.identity = (db.st_dev, db.st_ino)
            root = Path(directory) if directory is not None else Path.home()/'.pa-observer-locks'
            try: root.mkdir(mode=0o700)
            except FileExistsError: pass
            # Open the directory itself without following symlinks; all subsequent
            # operations are relative to its pinned descriptor.
            dfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                ds = os.fstat(dfd)
                if ds.st_uid != os.getuid() or stat.S_IMODE(ds.st_mode) != 0o700:
                    raise RuntimeError('journal lock directory must be owner-private (0700)')
                name = f'{db.st_dev}-{db.st_ino}.lock'
                self.path = root/name
                self.fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
                fs = os.fstat(self.fd)
                if (not stat.S_ISREG(fs.st_mode) or fs.st_uid != os.getuid()
                        or fs.st_nlink != 1 or stat.S_IMODE(fs.st_mode) != 0o600):
                    raise RuntimeError('unsafe journal sidecar')
            finally: os.close(dfd)
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Preserve exclusion against pre-sidecar versions on Linux.
                # Darwin flock shares SQLite's lock domain, so cannot lock DB there.
                if sys.platform != 'darwin':
                    fcntl.flock(self.db_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('journal already in use by another instance or process') from exc
            self.verify(database)
        except BaseException:
            self.close()
            raise

    def verify(self, database):
        actual = os.stat(database)
        if (actual.st_dev, actual.st_ino) != self.identity:
            raise RuntimeError('journal file changed while acquiring lock')

    def close(self):
        for attr in ('fd', 'db_fd'):
            fd = getattr(self, attr, None)
            if fd is not None:
                os.close(fd)
                setattr(self, attr, None)
