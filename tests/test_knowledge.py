import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kb', ROOT / 'knowledge/kb.py')
kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb)

class KnowledgeTests(unittest.TestCase):
    def setUp(self): self.data = kb.load()
    def test_integrity(self): self.assertEqual(kb.validate(self.data), [])
    def test_aliases(self):
        for query, expected in [('MM','measured-move'),('双底','double-bottom'),('micro gap','micro-gap'),('实际风险','actual-risk')]:
            self.assertEqual(kb.search(self.data,query)[0]['id'], expected)
    def test_empty_unknown(self):
        self.assertEqual(kb.search(self.data,''), [])
        self.assertEqual(kb.search(self.data,'xyznonexistent'), [])
    def test_dangling_source(self):
        self.data['concepts'][0]['sources'][0]['source_id']='unknown'
        self.assertTrue(kb.validate(self.data))
    def test_duplicate_id(self):
        self.data['concepts'].append(copy.deepcopy(self.data['concepts'][0]))
        self.assertTrue(kb.validate(self.data))
    def test_missing_provenance(self):
        self.data['sources'][0]['review_method']=''
        self.assertTrue(kb.validate(self.data))
    def test_bad_relation(self):
        self.data['concepts'][0]['related']=['missing']
        self.assertTrue(kb.validate(self.data))
    def test_index_current(self):
        self.assertEqual((ROOT/'knowledge/INDEX.md').read_text(),kb.render(self.data))
    def test_cli_outside_cwd(self):
        r=subprocess.run([sys.executable,str(ROOT/'knowledge/kb.py'),'show','micro-gap'],cwd='/tmp',capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['id'],'micro-gap')
    def test_cli_unknown(self):
        r=subprocess.run([sys.executable,str(ROOT/'knowledge/kb.py'),'show','no-such-id'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0)
    def test_no_implementation_claim(self):
        self.assertTrue(all(c['implementation_status']!='fully_implemented' for c in self.data['concepts']))
        self.assertTrue(all(c['engineering_interpretation']['status']=='design_guidance_not_source_prescribed_rule' for c in self.data['concepts']))

    def test_malformed_records(self):
        for data in [None, [], {}, {'schema_version':1,'sources':[None],'concepts':[[]]}]:
            self.assertTrue(kb.validate(data))
    def test_missing_locator(self):
        self.data['concepts'][0]['sources'][0]['locator']=''
        self.assertTrue(kb.validate(self.data))
    def test_invalid_status(self):
        self.data['concepts'][0]['evidence_status']='fully_proven'
        self.assertTrue(kb.validate(self.data))
    def test_category_filter(self):
        self.assertEqual(kb.search(self.data,'MM',category='risk'),[])
    def test_alias_case_and_unicode(self):
        self.assertEqual(kb.search(self.data,'  ｍｍ  ')[0]['id'],'measured-move')

    def test_wrong_method_type(self):
        self.data['sources'][0]['review_method']=[]
        self.assertTrue(kb.validate(self.data))

    def test_code_mappings(self):
        for c in self.data['concepts']:
            self.assertEqual(c['implementation_status'],c['code_mapping']['status'])
            for f in c['code_mapping']['files']:
                self.assertTrue((ROOT/f['path']).is_file())
                self.assertEqual(len(f['sha256']),64)
    def test_missing_code_mapping(self):
        del self.data['concepts'][0]['code_mapping']
        self.assertTrue(kb.validate(self.data))
    def test_search_causal_constraint(self):
        self.assertIn('micro-gap',[c['id'] for c in kb.search(self.data,'t+1收盘')])
    def test_index_provenance_fields(self):
        text=kb.render(self.data)
        self.assertIn('Reviewed at:',text)
        self.assertIn('Review scope:',text)
        self.assertIn('License:',text)
    def test_index_cannot_support_concept(self):
        ref=self.data['concepts'][0]['sources'][0]
        ref.update(source_id='brooks-course-index',support_role='concept_support')
        self.assertTrue(kb.validate(self.data))
    def test_bad_url_and_date(self):
        self.data['sources'][0]['url']='https://'
        self.data['sources'][0]['reviewed_at']='tomorrow'
        self.assertTrue(kb.validate(self.data))
    def test_alias_precision(self):
        byid={c['id']:c for c in self.data['concepts']}
        self.assertNotIn('突破失败',byid['failed-failure']['aliases'])
        self.assertNotIn('三推',byid['parabolic-wedge']['aliases'])
        self.assertIn('三推',byid['parabolic-wedge']['related_search_terms'])
    def test_substantive_card_requires_nonindex_support(self):
        self.data['concepts'][0]['sources']=[{
            'source_id':'brooks-course-index',
            'locator':'193 core entries',
            'support_role':'coverage_only',
        }]
        self.assertTrue(kb.validate(self.data))
    def test_counterexample_alone_not_concept_support(self):
        for ref in self.data['concepts'][0]['sources']:
            ref['support_role']='counterexample_support'
        self.assertTrue(kb.validate(self.data))
    def test_five_sample_review_boundaries(self):
        samples=[s for s in self.data['sources'] if s['review_method']=='full_captions_sampled_frames']
        self.assertEqual(len(samples),5)
        for s in samples:
            self.assertFalse(s['media_review']['audio_heard'])
            self.assertFalse(s['media_review']['continuous_video_review'])
            self.assertEqual(s['media_review']['caption_review'],'all_cues_fully_read')
        self.assertEqual(sum(s['media_review']['cues'] for s in samples),2109)
    def test_new_research_concepts(self):
        for query, expected in [('开盘突破模式','opening-breakout-mode'),('量度缺口与衰竭缺口','measuring-vs-exhaustion'),('确认与风险距离','confirmation-risk-tradeoff')]:
            self.assertEqual(kb.search(self.data,query)[0]['id'],expected)
    def test_foundation_gap_coverage(self):
        for query,expected in [('支撑阻力','support-resistance'),('Always In','always-in'),('微通道','micro-channel'),('ii','inside-sequences'),('最后旗形','final-flag'),('跟随','breakout-follow-through')]:
            self.assertEqual(kb.search(self.data,query)[0]['id'],expected)
    def test_claim_layers_explicit(self):
        for c in self.data['concepts']:
            self.assertEqual(c['claim_layers']['research_conclusion'],'source_grounded_paraphrase')
            self.assertEqual(c['claim_layers']['engineering_interpretation'],'project_synthesis_not_author_rule')
            self.assertEqual(c['claim_layers']['open_questions'],'unverified_research_questions')
    def test_missing_claim_layers_rejected(self):
        del self.data['concepts'][0]['claim_layers']
        self.assertTrue(kb.validate(self.data))
    def test_barbwire_is_related_not_synonym(self):
        c=next(c for c in self.data['concepts'] if c['id']=='tight-trading-range')
        self.assertNotIn('barbwire',c['aliases'])
        self.assertIn('barbwire',c['related_search_terms'])
    def test_microchannel_counterexample_provenance(self):
        c=next(c for c in self.data['concepts'] if c['id']=='micro-channel')
        self.assertTrue(any(r['source_id']=='brooks-37ab-sample' and r['support_role']=='counterexample_support' for r in c['sources']))
    def test_duplicate_summary_consistency(self):
        self.data['concepts'][0]['research_conclusion']='different meaning'
        self.assertTrue(kb.validate(self.data))
    def test_duplicate_constraints_consistency(self):
        self.data['concepts'][0]['engineering_interpretation']['constraints']=['different rule']
        self.assertTrue(kb.validate(self.data))
