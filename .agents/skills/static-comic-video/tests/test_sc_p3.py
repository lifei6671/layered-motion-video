import copy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from scripts.create_fixture import create_fixture
from static_comic.contracts import canonical
from static_comic.paths import write_bytes
from static_comic.project import compile_project,load_project
from static_comic.speech import evaluate,apply_alignment
from static_comic.speech_audio import prepare_audio,wav_info,service_json
from static_comic.speech_text import normalize,reading_map,check_overrides,make_plan
from speech_support import synthetic_windows,seed_alignment

HUMAN={"actor":"SYNTHETIC TEST ONLY","actor_role":"human","at":"2026-10-21T00:00:00Z","evidence":"Not a real approval"}


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.board=create_fixture(self.root)
        self.docs,self.hashes,_=load_project(self.root)
        self.script=(self.root/'input/script.txt').read_bytes().decode('utf-8-sig')
        self.samples=self.board['audio']['duration_samples']

    def override(self,entries):
        return {"schema_version":"1.0","script_sha256":self.hashes['input/script.txt'],
                "audio_sha256":self.hashes['input/voice.wav'],"storyboard_sha256":self.hashes['input/storyboard.json'],"entries":entries}

    def coarse(self,parts=None):
        if parts is None: parts=[self.script[a:b] for a,b in (s['script_range'] for s in self.board['shots'])]
        return {"backend_matches":True,"response":{"segments":[
            {"start":i*4+0.1,"end":min(i*4+3.8,self.samples/48000),"text":p} for i,p in enumerate(parts)]}}

    def test_numbers_percent_units_mapping_and_unicode(self):
        text,mapping=normalize('𠮷🙂\r\n增长28%，120元，2kg。')
        self.assertEqual(text,'𠮷增长百分之二十八一百二十元二千克')
        self.assertEqual(mapping[3:9],[[6,9]]*6)
        self.assertEqual(normalize('１０.５％')[0],'百分之十点五')

    def test_many_to_many_confirmed_reading(self):
        result=reading_map('API接口',[{"kind":"reading","script_range":[0,3],"reading":"应用程序"}])
        self.assertEqual(result['text'],'应用程序接口')
        self.assertEqual(result['source_ranges'][:4],[[0,3]]*4)
        self.assertEqual(result['origins'][:4],['manual_reading']*4)

    def test_ordered_repeated_sentence_and_missing_repeat(self):
        plan=make_plan(self.script,self.board,self.coarse(),[],self.samples)
        self.assertFalse(plan['anomalies'])
        self.assertLess(plan['windows'][0]['reading_range'][1],plan['windows'][2]['reading_range'][0])
        bad=self.coarse(['重复句。','𠮷🙂','结尾。'])
        plan=make_plan(self.script,self.board,bad,[],self.samples)
        self.assertTrue(any(a['kind']=='missing_or_truncated' for a in plan['anomalies']))

    def test_extra_and_truncated_are_localized(self):
        for parts in [['重复句。加读','重复句。𠮷🙂','结尾。'],['重复句。','重复句。𠮷🙂','结']]:
            plan=make_plan(self.script,self.board,self.coarse(parts),[],self.samples)
            self.assertTrue(plan['anomalies'])
            for issue in plan['anomalies']:
                self.assertTrue(issue['shot_ids']); self.assertEqual(len(issue['samples']),2)

    def test_seconds_are_offset_once_and_pcm_clock_is_not_channels(self):
        plan=make_plan(self.script,self.board,self.coarse(),[],self.samples)
        windows=synthetic_windows(plan)
        result=evaluate(self.board,plan,windows,[],self.samples)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['boundaries'][1]['sample'],196800)
        self.assertEqual(result['candidate_storyboard']['audio']['duration_samples'],self.samples)

    def test_missing_fallback_interpolation_wildcard_and_low_score(self):
        plan=make_plan(self.script,self.board,self.coarse(),[],self.samples)
        for change in ('fallback','interpolation','wildcard','score','zero','reverse'):
            raw=synthetic_windows(plan); chars=raw[1]['result']['segments'][0]['chars']
            if change=='fallback': raw[1]['result']['segments'][0]['chars']=[]
            if change=='interpolation': del chars[0]['score']
            if change=='wildcard': raw[1]['dictionary_characters']=[]
            if change=='score': chars[0]['score']=0.01
            if change=='zero': chars[0]['end']=chars[0]['start']
            if change=='reverse': chars[0]['start']=100
            with self.subTest(change=change):
                result=evaluate(self.board,plan,raw,[],self.samples)
                self.assertEqual(result['status'],'REVIEW_REQUIRED')
                self.assertNotEqual(result['boundaries'][1]['source'],'acoustic_aligned')

    def test_unplanned_transitions_do_not_block_alignment_or_become_authored_cuts(self):
        from static_comic.timeline import compile_timing
        for shot in self.board['shots']:
            shot['transition_out'] = None
        plan = make_plan(self.script, self.board, self.coarse(), [], self.samples)
        result = evaluate(self.board, plan, synthetic_windows(plan), [], self.samples)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(all(s['transition_out'] is None for s in result['candidate_storyboard']['shots']))
        self.assertTrue(all(s['transition_out'] is None for s in self.board['shots']))
        with self.assertRaisesRegex(ValueError, 'transition must reference'):
            compile_timing(result['candidate_storyboard'])

    def test_unplanned_transitions_still_reject_bad_clock_and_authored_effect(self):
        for case in ('nonmonotonic', 'zero_frame', 'authored_effect'):
            board = copy.deepcopy(self.board)
            board['shots'][0]['transition_out'] = None
            entries = []
            if case == 'authored_effect':
                board['shots'][1]['transition_out']['duration_frames'] = 1000
            else:
                entries = [{'kind': 'boundary', 'from_shot_id': 'SHOT-001', 'to_shot_id': 'SHOT-002',
                            'sample': 0 if case == 'nonmonotonic' else 1, 'reason': 'Test', 'human': HUMAN}]
            plan = make_plan(self.script, board, self.coarse(), entries, self.samples)
            with self.subTest(case=case):
                result = evaluate(board, plan, synthetic_windows(plan), entries, self.samples)
                self.assertEqual(result['status'], 'REVIEW_REQUIRED')
                self.assertIsNone(result['candidate_storyboard'])

    def test_manual_boundary_resolves_timing_but_never_content(self):
        entry={"kind":"boundary","from_shot_id":"SHOT-001","to_shot_id":"SHOT-002","sample":200000,"reason":"Test","human":HUMAN}
        plan=make_plan(self.script,self.board,self.coarse(),[entry],self.samples)
        raw=synthetic_windows(plan); raw[1]['result']['segments'][0]['chars'][0]['score']=0.01
        result=evaluate(self.board,plan,raw,[entry],self.samples)
        self.assertEqual(result['status'],'PASS'); self.assertEqual(result['boundaries'][1]['source'],'manual_confirmed')
        plan['anomalies'].append({'kind':'missing_or_truncated'})
        result=evaluate(self.board,plan,raw,[entry],self.samples)
        self.assertEqual(result['status'],'REVIEW_REQUIRED')

    def test_overrides_stale_conflicts_bounds_and_receipt(self):
        valid={"kind":"reading","script_range":[0,1],"reading":"重","reason":"Test","human":HUMAN}
        self.assertEqual(check_overrides(self.override([valid]),self.board,self.script,self.hashes,self.samples),[valid])
        candidates=[self.override([valid,valid])]
        stale=self.override([valid]); stale['audio_sha256']='0'*64; candidates.append(stale)
        wrong=copy.deepcopy(valid); wrong['human']['at']='2026-10-21'; candidates.append(self.override([wrong]))
        for item in candidates:
            with self.assertRaises(ValueError): check_overrides(item,self.board,self.script,self.hashes,self.samples)
        window={"kind":"window","script_range":[0,1],"samples":[0,self.samples+1],"reason":"Test","human":HUMAN}
        with self.assertRaises(ValueError): check_overrides(self.override([window]),self.board,self.script,self.hashes,self.samples)
        boundary={"kind":"boundary","from_shot_id":"SHOT-001","to_shot_id":"SHOT-003","sample":1000,"reason":"Test","human":HUMAN}
        with self.assertRaises(ValueError): check_overrides(self.override([boundary]),self.board,self.script,self.hashes,self.samples)

    def test_manual_confirmation_recovers_full_fallback_and_first_shot_internal_gap(self):
        entry={"kind":"boundary","from_shot_id":"SHOT-001","to_shot_id":"SHOT-002","sample":200000,"reason":"Listened to both adjacent shots and confirmed this switch","human":HUMAN}
        plan=make_plan(self.script,self.board,self.coarse(),[entry],self.samples)
        for case in ('full_fallback','first_internal'):
            raw=synthetic_windows(plan)
            if case=='full_fallback': raw[1]['result']['segments'][0]['chars']=[]
            else: raw[0]['result']['segments'][0]['chars'][1]['score']=0.01
            with self.subTest(case=case):
                result=evaluate(self.board,plan,raw,[entry],self.samples)
                self.assertEqual(result['status'],'PASS')
                index=1 if case=='full_fallback' else 0
                self.assertEqual(result['speech_intervals'][index]['source'],'coarse_segment')
                self.assertEqual(result['candidate_storyboard']['shots'][index]['timing_source'],'manual_confirmed')
                self.assertTrue(result['warnings'])
                self.assertTrue(any(c['source']!='acoustic_aligned' for c in result['characters']))
                again=evaluate(self.board,plan,raw,[entry],self.samples)
                self.assertEqual(result,again)
                plan_bad=copy.deepcopy(plan); plan_bad['anomalies'].append({'kind':'missing_or_truncated'})
                self.assertEqual(evaluate(self.board,plan_bad,raw,[entry],self.samples)['status'],'REVIEW_REQUIRED')

    def test_window_override_replaces_not_duplicates_offset(self):
        entry={"kind":"window","script_range":self.board['shots'][1]['script_range'],"samples":[200001,370000],"reason":"Test","human":HUMAN}
        plan=make_plan(self.script,self.board,self.coarse(),[entry],self.samples)
        self.assertEqual(plan['windows'][1]['origin_samples'],200001)
        self.assertEqual(plan['windows'][1]['source'],'manual_window')
        result=evaluate(self.board,plan,synthetic_windows(plan),[entry],self.samples)
        self.assertEqual(result['boundaries'][1]['sample'],200001)

    def test_backend_fallback_and_overlapping_segments_block(self):
        coarse=self.coarse(); coarse['backend_matches']=False
        self.assertEqual(make_plan(self.script,self.board,coarse,[],self.samples)['anomalies'][0]['kind'],'backend_changed')
        coarse=self.coarse(); coarse['response']['segments'][1]['start']=1
        plan=make_plan(self.script,self.board,coarse,[],self.samples)
        self.assertIn('invalid_asr_window',[a['kind'] for a in plan['anomalies']])

    def test_confirmed_window_recovers_bad_coarse_time_and_first_shot_fallback(self):
        coarse=self.coarse(); coarse['response']['segments'][-1]['end']=100
        entry={"kind":"window","script_range":self.board['shots'][-1]['script_range'],"samples":[388800,566400],"reason":"Known test window","human":HUMAN}
        plan=make_plan(self.script,self.board,coarse,[entry],self.samples)
        self.assertFalse(plan['anomalies']); self.assertTrue(plan['resolved_timing_anomalies'])
        self.assertEqual(evaluate(self.board,plan,synthetic_windows(plan),[entry],self.samples)['status'],'PASS')
        entry['script_range']=self.board['shots'][0]['script_range']; entry['samples']=[4800,182400]
        plan=make_plan(self.script,self.board,self.coarse(),[entry],self.samples)
        raw=synthetic_windows(plan); raw[0]['result']['segments'][0]['chars']=[]
        result=evaluate(self.board,plan,raw,[entry],self.samples)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['speech_intervals'][0]['source'],'manual_window')
        coarse=self.coarse(); coarse['response']['segments'][-1]['end']=100
        plan=make_plan(self.script,self.board,coarse,[],self.samples)
        self.assertIn('invalid_asr_window',[a['kind'] for a in plan['anomalies']])

    def test_replay_is_deterministic_and_tampering_or_staleness_fails(self):
        aligned=seed_alignment(self.root,True)
        one=compile_project(self.root,technical_fixture=True,write=False)
        two=compile_project(self.root,technical_fixture=True,write=False)
        self.assertEqual(one,two)
        aligned['boundaries'][1]['sample']+=1
        write_bytes(self.root,'work/alignment/aligned.json',canonical(aligned))
        with self.assertRaisesRegex(ValueError,'edited'): compile_project(self.root,technical_fixture=True,write=False)
        seed_alignment(self.root,True)
        self.board['shots'][0]['narrative']='changed'
        write_bytes(self.root,'input/storyboard.json',canonical(self.board))
        with self.assertRaisesRegex(ValueError,'Stale'): compile_project(self.root,technical_fixture=True,write=False)

    def test_audio_edit_invalidates_evidence(self):
        seed_alignment(self.root,True)
        p=self.root/'work/audio/master_48k.wav'; data=p.read_bytes(); p.write_bytes(data[:-2]+b'12')
        with self.assertRaisesRegex(ValueError,'PCM audio changed'): compile_project(self.root,technical_fixture=True,write=False)

    def test_production_cannot_bypass_alignment_or_use_technical_evidence(self):
        from test_sc_p1 import approved_test_project
        approved_test_project(self.root)
        (self.root/'work/alignment/aligned.json').unlink()
        with self.assertRaisesRegex(ValueError,'Missing'): compile_project(self.root,write=False)
        seed_alignment(self.root,True)
        with self.assertRaisesRegex(ValueError,'incompatible'): compile_project(self.root,write=False)

    def test_real_ffmpeg_pcm_retains_leading_trailing_and_internal_silence(self):
        # Distinct nonzero pulses amid silence; stereo PCM frames are not byte/sample counts.
        with wave.open(str(self.root/'input/voice.wav'),'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
            w.writeframes(b'\0\0'*2*4800+b'\x10\x27'*2*4800+b'\0\0'*2*9600+b'\x20\x4e'*2*4800+b'\0\0'*2*4800)
        info=prepare_audio(self.root,'input/voice.wav')
        self.assertEqual(info['master']['samples'],28800); self.assertEqual(info['align']['samples'],9600)
        with wave.open(str(self.root/'work/audio/master_48k.wav')) as w:
            self.assertEqual(w.readframes(4800),b'\0\0'*2*4800)
            self.assertEqual(w.readframes(4800),b'\x10\x27'*2*4800)
            self.assertEqual(w.readframes(9600),b'\0\0'*2*9600)
            w.readframes(4800); self.assertEqual(w.readframes(4800),b'\0\0'*2*4800)

    def test_nonlocal_service_rejected_before_upload(self):
        for url in ('https://example.com','http://127.0.0.1/x','http://user@localhost:13900'):
            with self.assertRaises(ValueError): service_json(url,'/health')


if __name__=='__main__': unittest.main()
