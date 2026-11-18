import os
import tempfile
import unittest
from pathlib import Path
from pa_lens.service import Journal

class PortableJournalLockTests(unittest.TestCase):
    def test_disk_journal_can_use_wal_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.db'
            j=Journal(path)
            try:self.assertEqual(j.conn.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            finally:j.close()
            Journal(path).close()

    def test_aliases_share_lock_and_sidecar_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.db'; j=Journal(path)
            try:
                hard=Path(tmp)/'hard.db'; os.link(path,hard)
                symlink=Path(tmp)/'sym.db'; symlink.symlink_to(path)
                for alias in (hard,symlink):
                    with self.assertRaisesRegex(RuntimeError,'already in use'):Journal(alias)
                lock_path=j._file_lock.path
                self.assertTrue(lock_path.is_file())
            finally:j.close()
            self.assertTrue(lock_path.is_file())
            Journal(path).close()

    def test_unsafe_sidecar_and_directory_are_rejected(self):
        from pa_lens.journal_lock import JournalLock
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'x.db'; db.touch(); info=db.stat()
            locks=Path(tmp)/'locks'; locks.mkdir(mode=0o700)
            side=locks/f'{info.st_dev}-{info.st_ino}.lock'
            target=Path(tmp)/'target'; target.touch(mode=0o600)
            side.symlink_to(target)
            with self.assertRaises(OSError): JournalLock(db, locks)
            side.unlink(); os.link(target, side)
            with self.assertRaisesRegex(RuntimeError,'unsafe'): JournalLock(db, locks)
            side.unlink(); locks.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError,'owner-private'):JournalLock(db,locks)
