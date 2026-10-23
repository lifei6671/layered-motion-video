"""Regression checks for resource signatures, priority, tail trimming and batch frames."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from static_comic import emphasis_preview, human_review
from static_comic.contracts import bytes_digest, canonical, digest, read_json
from static_comic.emphasis import DEFAULT_POLICY, verify_asset
from static_comic.emphasis_cli import resource_workflow
from static_comic.emphasis_timing import compile_events
from static_comic.media import file_hash, run


class EmphasisRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sc-emphasis-repairs-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key_patch = patch.object(human_review, 'KEY_PATH', self.root/'test-only-confirmation.key')
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def put(self, path, content):
        target=self.root/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content if isinstance(content,bytes) else canonical(content))

    def resource(self):
        source=b'test-only fixed font fixture bytes'
        evidence=b'test-only license text'
        self.put('assets/fonts/f.ttf',source)
        self.put('assets/fonts/LICENSE.txt',evidence)
        asset={'asset_id':'f','path':'assets/fonts/f.ttf','sha256':bytes_digest(source),
            'source_kind':'local_created','source_uri':'local:test-only','author':'TEST ONLY',
            'license':'TEST ONLY','usage_scope':'technical testing',
            'license_evidence':{'path':'assets/fonts/LICENSE.txt','sha256':bytes_digest(evidence)},
            'review_status':'APPROVED','family':'TEST ONLY'}
        self.put('assets/fonts/manifest.json',{'schema_version':'1.0','assets':[asset]})
        return asset

    def test_signed_resource_gate_binding_and_replay(self):
        asset=self.resource()
        with self.assertRaisesRegex(ValueError,'signed resource approval'):
            verify_asset(self.root,asset,kind='fonts',technical=False)
        proposal=resource_workflow(self.root,'prepare-resource',kind='font',asset_id='f')
        value=read_json((self.root/proposal['path']).read_bytes())
        # Sign only against an isolated test key and test fixture; this is not
        # an actual user's production decision.
        signed=human_review.sign({**value,'human':{'actor':'TEST ONLY','actor_role':'human',
            'at':'2026-01-01T00:00:00+00:00','evidence':'TEST ONLY'}},
            'resources','local_terminal')
        self.put('review/signed.json',signed)
        self.assertEqual(resource_workflow(self.root,'approve-resource',signed_file='review/signed.json')['status'],
                         'RESOURCE_REVIEW_APPLIED')
        self.assertEqual(verify_asset(self.root,asset,kind='fonts',technical=False),asset)
        wrong=deepcopy(signed)
        wrong['human']['confirmation']['scope']='preview'
        self.put('review/wrong.json',wrong)
        with self.assertRaisesRegex(ValueError,'confirmation'):
            resource_workflow(self.root,'approve-resource',signed_file='review/wrong.json')
        changed={**asset,'usage_scope':'another usage'}
        self.put('assets/fonts/manifest.json',{'schema_version':'1.0','assets':[changed]})
        with self.assertRaisesRegex(ValueError,'stale'):
            verify_asset(self.root,changed,kind='fonts',technical=False)

    def fixture_compile(self, *,visuals=None,sounds=None,second_silent=False):
        policy=deepcopy(DEFAULT_POLICY)
        policy['mode']='mixed'
        policy['visual']['enabled']=bool(visuals)
        policy['audio']['enabled']=bool(sounds)
        plan={'visual_events':visuals or [],'audio_events':sounds or [],'excluded':[],
              'shot_decisions':[{'shot_id':'SHOT-001','text_decision':'auto','sfx_decision':'allow'},
                                {'shot_id':'SHOT-002','text_decision':'skip','sfx_decision':'silence' if second_silent else 'allow'}]}
        board={'shots':[{'id':'SHOT-001','script_range':[0,4]},
                        {'id':'SHOT-002','script_range':[4,8]}],
               'audio':{'duration_samples':320000}}
        execution=[{'id':'SHOT-001','start_frame':0,'end_frame':100,'transition_out':None},
                   {'id':'SHOT-002','start_frame':100,'end_frame':200,'transition_out':None}]
        observation={'artifact_kind':'technical_fixture','shots':[
            {'shot_id':'SHOT-001','emotion':'neutral'},
            {'shot_id':'SHOT-002','emotion':'neutral'}]}
        ext={'policy':policy,'plan':plan,
             'fonts':{'f':{'asset_id':'f','sha256':'a'*64,'path':'assets/fonts/f.ttf'}} if visuals else {},
             'sfx':{'s':{'asset_id':'s','sha256':'b'*64}} if sounds else {},
             'input_hashes':{}}
        return ext,board,execution,observation

    def test_high_importance_wins_collision_over_low_id(self):
        base={'shot_id':'SHOT-001','script_range':[0,2],'text':'重复',
              'semantic_type':'concept','preset':'soft_rise','tier':1,
              'layout':{'preset':'upper_left'},'pinned':False,'source':'rules'}
        lo={**base,'id':'A-low','importance':'low'}
        hi={**base,'id':'Z-high','importance':'high'}
        ext,board,clock,obs=self.fixture_compile(visuals=[lo,hi])
        layout={'x':.2,'y':.2,'width':.1,'height':.1,'font_size':72}
        detail={'reason_code':'SAFE_REGION','color':'#ffffff','stroke_color':'#000000'}
        with patch('static_comic.emphasis_timing.observe',return_value=(obs,{})), \
             patch('static_comic.emphasis_timing.choose_layout',return_value=(layout,detail)), \
             patch('static_comic.emphasis_timing.speech_samples',return_value=[96000,102000]), \
             patch('static_comic.emphasis_timing.read_bytes',return_value=b'font'):
            result=compile_events(self.root,ext,board,clock,[{},{}],{},technical=True,write=False)
        self.assertEqual([e['id'] for e in result['visual']],['Z-high'])
        self.assertEqual(next(e for e in result['diagnostics'] if e['id']=='A-low')['reason_code'],'DENSITY_BUDGET')

    def test_tail_trim_only_when_opted_in_and_fades(self):
        base={'id':'snd','kind':'scene','sfx_asset_id':'s',
              'anchor':{'type':'shot_start','shot_id':'SHOT-001','offset_samples':0},
              'gain_db':-12,'fade_in_samples':0,'fade_out_samples':0,
              'pinned':False,'source':'rules'}
        normalized={'samples':200000,'normalized_path':'work/audio/sfx/audio.wav',
                    'normalized_sha256':'c'*64}
        with patch('static_comic.emphasis_timing.observe') as observe, \
             patch('static_comic.sfx_library.normalize_asset',return_value=normalized):
            for enabled in (False,True):
                ext,board,clock,obs=self.fixture_compile(sounds=[{**base,'allow_tail_trim':enabled}],second_silent=True)
                observe.return_value=(obs,{})
                result=compile_events(self.root,ext,board,clock,[{},{}],{},technical=True,write=False)
                if enabled:
                    self.assertEqual(result['sfx'][0]['play_samples'],160000)
                    self.assertGreater(result['sfx'][0]['fade_out_samples'],0)
                else:
                    self.assertFalse(result['sfx'])
                    self.assertEqual(result['diagnostics'][0]['reason_code'],'SILENCE_TAIL_CONFLICT')

    def test_marker_batch_deduplicates_frames(self):
        video=self.root/'clip.mp4'
        run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi',
             '-i','color=c=blue:s=160x90:r=30:d=1','-frames:v','12',
             '-c:v','libx264',str(video)])
        frames,sha,batches=emphasis_preview.extract_markers(str(video),[11,0,3,3,11])
        self.assertEqual((sorted(frames),batches),([0,3,11],1))
        self.assertEqual(sha,file_hash(video))
        self.assertTrue(all(data.startswith(bytes((137, 80, 78, 71))) for data in frames.values()))


if __name__=='__main__':
    unittest.main()
