from human_support import simulated
import copy
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib

from PIL import Image, ImageCms
from scripts.create_fixture import create_fixture
from static_comic.contracts import bytes_digest, canonical, digest, read_json, validate
from static_comic.images import motion_at, orient_bbox, prepare_image
from static_comic.paths import resolve_path
from static_comic.project import check_source_policy, compile_project, load_project
from static_comic.timeline import compile_timing, frame_at, seconds_to_samples, total_frames

BASE = Path(__file__).resolve().parents[1]
# Synthetic receipts only inside temporary test projects. Not actual user approval.
TEST_HUMAN = {"actor": "TEST ONLY", "actor_role": "human", "at": "2026-10-21T00:00:00Z",
              "evidence": "Synthetic test receipt; never use for real production"}


def save(root, name, value):
    (root / name).write_bytes(canonical(value) + b"\n")


def read(root, name):
    return read_json((root / name).read_bytes())


def approved_test_project(root, *, semantic=True):
    board = read(root, "input/storyboard.json")
    policy = read(root, "input/image_source_policy.json")
    manifest = read(root, "assets/images/manifest.json")
    policy["status"] = "APPROVED"
    policy["confirmation"] = simulated("policy", {"human": TEST_HUMAN,
                              "payload_sha256": digest({k:v for k,v in policy.items() if k != "confirmation"})})
    receipts = []
    for shot, asset in zip(board["shots"], manifest["assets"]):
        shot["timing_source"] = "manual_confirmed"
        if shot["transition_out"]:
            shot["transition_out"]["planning_source"] = "human"
        asset.update(purpose="production", review_status="APPROVED", reviewer=TEST_HUMAN)
        asset["license"]["publication_allowed"] = True
        receipts.append({"shot_id": shot["id"], "status": "APPROVED", "image_sha256": asset["sha256"],
                         "asset_sha256": digest(asset), "policy_sha256": digest(policy), "human": TEST_HUMAN})
    for name, value in [("input/storyboard.json",board),("input/image_source_policy.json",policy),
                        ("assets/images/manifest.json",manifest),
                        ("review/image_approvals.json",{"schema_version":"1.0","receipts":receipts})]:
        save(root,name,value)
    from image_support import seed_supply
    seed_supply(root, board)
    image_receipts = {r["shot_id"]: r for r in read(root, "review/image_approvals.json")["receipts"]}
    for index, shot in enumerate(board["shots"][:-1]):
        if shot["transition_out"]:
            shot["transition_out"]["image_approval_hashes"] = [
                digest(image_receipts[shot["id"]]), digest(image_receipts[board["shots"][index + 1]["id"]])]
    save(root, "input/storyboard.json", board)
    from speech_support import seed_alignment
    seed_alignment(root)
    if semantic:
        from transition_support import seed_transitions
        seed_transitions(root)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = create_fixture(self.root)

    def compile(self, **kwargs):
        return compile_project(self.root, technical_fixture=True, **kwargs)

    def test_clock_fixture_and_determinism(self):
        one = self.compile()
        before = {p:(self.root/p).read_bytes() for p in one["written"]}
        two = self.compile()
        self.assertEqual(one["timeline"], two["timeline"])
        self.assertEqual(before, {p:(self.root/p).read_bytes() for p in two["written"]})
        shots = one["props"]["shots"]
        self.assertEqual(one["total_frames"],360)
        self.assertEqual([s["logical_frames"] for s in shots],[120,150,90])
        self.assertEqual([s["physical_frames"] for s in shots],[120,174,90])
        self.assertEqual([(s["transition_out"]["transition_start_frame"],s["transition_out"]["transition_end_frame"])
                          for s in shots[:-1]],[(108,120),(270,282)])
        self.assertEqual(sum(s["logical_frames"] for s in shots),360)
        self.assertEqual(sum(s["physical_frames"] for s in shots)-24,360)

    def test_validate_has_no_writes(self):
        self.assertEqual(self.compile(write=False)["written"],[])
        self.assertFalse((self.root/"work/remotion").exists())

    def test_unicode_raw_bytes_and_offsets(self):
        _, _, index = load_project(self.root)
        raw=(self.root/"input/script.txt").read_bytes()
        text=raw.decode("utf-8-sig")
        offsets=index["codepoint_to_raw_utf8_byte"]
        self.assertEqual(offsets[0],3)
        self.assertEqual(offsets[-1],len(raw))
        for i,char in enumerate(text):
            self.assertEqual(raw[offsets[i]:offsets[i+1]].decode("utf-8"),char)
        self.assertIn("𠮷🙂\r\n",text)
        self.assertEqual(text.count("重复句。"),2)
        (self.root/"input/script.txt").write_bytes(raw.replace(b"\r\n",b"\n"))
        with self.assertRaisesRegex(ValueError,"Original script bytes"):
            load_project(self.root)

    def test_script_gaps_and_invalid_references(self):
        for change in ("range","duplicate","next"):
            board=copy.deepcopy(self.board)
            if change=="range": board["shots"][1]["script_range"][0]+=1
            if change=="duplicate": board["shots"][1]["id"]=board["shots"][0]["id"]
            if change=="next": board["shots"][0]["transition_out"]["to_shot_id"]="SHOT-099"
            save(self.root,"input/storyboard.json",board)
            with self.subTest(change=change), self.assertRaises(ValueError): self.compile(write=False)

    def test_pending_policy_never_stages_production(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_POLICY_PENDING"): compile_project(self.root)
        self.assertFalse((self.root/"work/remotion/public").exists())

    def test_production_requires_receipts_and_unchanged_metadata(self):
        approved_test_project(self.root)
        original=read(self.root,"review/image_approvals.json")
        save(self.root,"review/image_approvals.json",{"schema_version":"1.0","receipts":[]})
        with self.assertRaisesRegex(ValueError,"image existence"): compile_project(self.root)
        save(self.root,"review/image_approvals.json",original)
        manifest=read(self.root,"assets/images/manifest.json")
        manifest["assets"][0]["license"]["publication_allowed"]=False
        save(self.root,"assets/images/manifest.json",manifest)
        with self.assertRaisesRegex(ValueError,"approval is stale"): compile_project(self.root)

    def test_approved_staging_is_copy_and_contains_only_images(self):
        approved_test_project(self.root)
        result=compile_project(self.root)
        public=self.root/"work/remotion/public"
        files=list(public.rglob("*"))
        self.assertEqual(len([p for p in files if p.is_file()]),3)
        self.assertTrue(all(p.suffix==".png" for p in files if p.is_file()))
        staged=public/result["props"]["shots"][0]["staged_image"]
        snapshot=staged.read_bytes()
        original=self.root/"assets/images/shot_0001.png"
        self.assertFalse(os.path.samefile(staged, original))
        original.write_bytes(b"replaced")
        self.assertEqual(staged.read_bytes(),snapshot)
        with self.assertRaisesRegex(ValueError,"image bytes changed"): compile_project(self.root)
        self.assertEqual(staged.read_bytes(),snapshot)

    def test_changed_approval_metadata_is_stale(self):
        approved_test_project(self.root)
        manifest=read(self.root,"assets/images/manifest.json")
        manifest["assets"][0]["author"]="different author"
        save(self.root,"assets/images/manifest.json",manifest)
        with self.assertRaisesRegex(ValueError,"approval is stale"): compile_project(self.root)

    def test_source_change_requires_confirmation(self):
        approved_test_project(self.root)
        policy=read(self.root,"input/image_source_policy.json")
        policy["default_channel"]="other"
        save(self.root,"input/image_source_policy.json",policy)
        with self.assertRaisesRegex(ValueError,"confirmation is stale"): compile_project(self.root)

    def test_mixed_policy_requires_every_shot(self):
        policy=read(self.root,"input/image_source_policy.json")
        policy.update(mode="mixed",status="APPROVED",default_channel=None)
        policy["confirmation"]=simulated("policy", {"human":TEST_HUMAN,
            "payload_sha256":digest({k:v for k,v in policy.items() if k!="confirmation"})})
        with self.assertRaisesRegex(ValueError,"every shot"): check_source_policy(policy,self.board["shots"])
        policy["shots"]={s["id"]:{"source_mode":"manual_generate","channel":"technical-fixture"} for s in self.board["shots"]}
        policy["confirmation"]["payload_sha256"]=digest({k:v for k,v in policy.items() if k!="confirmation"})
        policy["confirmation"] = simulated("policy", policy["confirmation"])
        self.assertEqual(len(check_source_policy(policy,self.board["shots"])),3)

    def test_candidate_and_reference_cannot_stage(self):
        approved_test_project(self.root)
        manifest=read(self.root,"assets/images/manifest.json")
        for value in ("reference_only","technical_fixture"):
            manifest["assets"][0]["purpose"]=value
            save(self.root,"assets/images/manifest.json",manifest)
            with self.assertRaisesRegex(ValueError,"REVIEW_REQUIRED"): compile_project(self.root)
        manifest["assets"][0]["path"]="work/images/candidates/example.png"
        save(self.root,"assets/images/manifest.json",manifest)
        with self.assertRaisesRegex(ValueError,"candidate"): compile_project(self.root)

    def test_nonimage_public_data_is_not_exposed_or_removed(self):
        public=self.root/"work/remotion/technical/public"
        public.mkdir(parents=True)
        (public/"secret.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError,"non-staged"): self.compile()
        self.assertEqual((public/"secret.txt").read_text(),"keep")
        self.assertFalse((self.root/"work/remotion/technical/props.json").exists())

    def test_stale_overrides_and_nonempty_overrides_need_alignment(self):
        override={"schema_version":"1.0","script_sha256":self.board["script_sha256"],
                  "audio_sha256":self.board["audio"]["sha256"],"storyboard_sha256":"0"*64,"entries":[]}
        save(self.root,"input/overrides.json",override)
        with self.assertRaisesRegex(ValueError,"Stale overrides"): load_project(self.root)
        override["storyboard_sha256"]=bytes_digest((self.root/"input/storyboard.json").read_bytes())
        override["entries"]=[{"kind":"reading","script_range":[0,1],"reading":"test","reason":"test","human":TEST_HUMAN}]
        save(self.root,"input/overrides.json",override)
        self.assertEqual(load_project(self.root)[0]["overrides"],override)
        with self.assertRaisesRegex(ValueError,"SC-P3"): self.compile(write=False)

    def test_stale_transition_evidence(self):
        self.board["shots"][0]["transition_out"]["image_hashes"][0]="0"*64
        save(self.root,"input/storyboard.json",self.board)
        with self.assertRaisesRegex(ValueError,"visual evidence is stale"): self.compile()

    def test_third_party_requires_source_and_review_not_license_declaration(self):
        approved_test_project(self.root)
        from static_comic.project import check_approval
        shot=self.board["shots"][0]
        asset=read(self.root,"assets/images/manifest.json")["assets"][0]
        asset.update(source_mode="third_party_retrieve",channel="library",source_uri="local:test",query="")
        assignment={"source_mode":"third_party_retrieve","channel":"library"}
        with self.assertRaisesRegex(ValueError,"source URL and query"):
            check_approval(shot,asset,"0"*64,assignment,{})
        asset.update(source_uri="https://example.test/image",query="licensed comic")
        del asset["license"]
        with self.assertRaisesRegex(ValueError,"image existence"):
            check_approval(shot,asset,"0"*64,assignment,{})

    def test_cli_fails_without_traceback_for_pending(self):
        result=subprocess.run([sys.executable,"-m","static_comic","compile","--project",str(self.root)],
                              cwd=BASE,capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stderr)["status"],"FAIL")

    def assert_cli_input_failure(self, pattern, project=None):
        result=subprocess.run([sys.executable,"-m","static_comic","compile","--project",str(project or self.root),
                               "--technical-fixture"],cwd=BASE,capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stderr)
        failure=json.loads(result.stderr)
        self.assertEqual(failure["status"],"FAIL")
        self.assertRegex(failure["error"],pattern)
        self.assertNotIn("Traceback",result.stderr)
        self.assertFalse((self.root/"work/remotion").exists())

    def test_cli_yaml_syntax_and_nonjson_values(self):
        for content,pattern in (("width: [broken","invalid YAML"),
                                ("width: 2026-10-21","non-JSON"),
                                ("width: !!set {a: null}","non-JSON")):
            with self.subTest(content=content):
                (self.root/"input/render.yaml").write_text(content,encoding="utf-8")
                self.assert_cli_input_failure(pattern)

    def test_cli_png_decoder_pixel_limit(self):
        header=b"IHDR"+struct.pack(">IIBBBBB",20000,20000,8,2,0,0,0)
        raw=b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+header+struct.pack(">I",zlib.crc32(header))
        raw+=b"\x00\x00\x00\x00IDAT\x35\xaf\x06\x1e"
        (self.root/self.board["shots"][0]["image"]).write_bytes(raw)
        manifest=read(self.root,"assets/images/manifest.json")
        manifest["assets"][0]["sha256"]=bytes_digest(raw)
        save(self.root,"assets/images/manifest.json",manifest)
        self.board["shots"][0]["transition_out"]["image_hashes"][0]=bytes_digest(raw)
        save(self.root,"input/storyboard.json",self.board)
        self.assert_cli_input_failure("pixel limit")

    def test_cli_unicode_error_is_valid_json_on_legacy_console(self):
        self.assert_cli_input_failure(".*", self.root/"missing-𠮷🙂")


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.board=create_fixture(Path(self.temp.name))

    def test_decimal_clock_once_and_half_up(self):
        self.assertEqual(seconds_to_samples("11.981"),575088)
        self.assertEqual(total_frames(575088),360)
        self.assertEqual(frame_at(800),1)
        self.assertEqual(frame_at(799),0)
        self.assertEqual(seconds_to_samples("0.00003125",100),102)
        for invalid in ("NaN","Infinity","-1"):
            with self.assertRaises(ValueError): seconds_to_samples(invalid)

    def test_placements_odd_even(self):
        for placement in ("start_at_anchor","end_at_anchor","center_on_anchor"):
            for length in (11,12):
                tr=self.board["shots"][0]["transition_out"]
                tr.update(placement=placement,duration_frames=length)
                _,shots=compile_timing(self.board)
                compiled=shots[0]["transition_out"]
                pre={"start_at_anchor":0,"end_at_anchor":length,"center_on_anchor":length//2}[placement]
                self.assertEqual((compiled["pre_frames"],compiled["post_frames"]),(pre,length-pre))
                self.assertEqual(compiled["transition_start_frame"],120-pre)

    def test_absolute_rounding_not_accumulated(self):
        # Two 0.49-frame spans: independent rounding loses the first full frame.
        self.board["shots"][1]["start_samples"]=784
        self.board["shots"][2]["start_samples"]=1568
        with self.assertRaisesRegex(ValueError,"shorter than one frame"): compile_timing(self.board)
        boundaries=[frame_at(n*2401) for n in range(1001)]
        self.assertEqual(sum(b-a for a,b in zip(boundaries,boundaries[1:])),frame_at(2401000))
        self.assertNotEqual(frame_at(2401)*1000,frame_at(2401000))

    def test_conflicting_and_outside_windows(self):
        self.board["shots"][0]["transition_out"].update(placement="start_at_anchor",duration_frames=150)
        with self.assertRaisesRegex(ValueError,"SHOT-002.*non-transition"): compile_timing(self.board)
        self.board["shots"][0]["transition_out"].update(placement="end_at_anchor",duration_frames=121)
        with self.assertRaisesRegex(ValueError,"SHOT-001.*outside"): compile_timing(self.board)
        self.board["shots"][0]["transition_out"]["duration_frames"]=12
        self.board["shots"][1]["transition_out"]["duration_frames"]=91
        with self.assertRaisesRegex(ValueError,"SHOT-002.*outside"): compile_timing(self.board)

    def test_cuts_and_single_frame(self):
        self.board["shots"]=self.board["shots"][:1]
        self.board["shots"][0]["transition_out"]=None
        self.board["audio"]["duration_samples"]=1600
        self.board["shots"][0]["speech_interval_samples"]=[0,1600]
        total,shots=compile_timing(self.board)
        self.assertEqual(total,1)
        self.assertEqual(shots[0]["physical_frames"],1)

    def test_holds_freeze_motion(self):
        _,timing=compile_timing(self.board)
        clock=timing[1]
        motion=self.board["shots"][1]["motion"]
        values=[motion_at(motion,f,clock,1920,1080) for f in range(clock["physical_frames"])]
        self.assertEqual(values[0],values[12])
        self.assertEqual(values[-1],values[161])
        self.assertEqual(values[-1]["logical_frame"],149)


class BoundaryTests(unittest.TestCase):
    def test_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as root:
            for path in ("../outside","/root","C:/x","C:x","//server/share","a\\b","a//b","a/./b",
                         "a/b:ads","a/CON.png","a/file.","a/file ","a?b","a\x00b"):
                with self.subTest(path=path), self.assertRaises(ValueError): resolve_path(root,path,output=True)
            self.assertEqual(resolve_path(root,"assets/images/shot_0001.png"),Path(root)/"assets/images/shot_0001.png")
            (Path(root)/"work").write_text("not a directory")
            with self.assertRaisesRegex(ValueError,"ancestor"): resolve_path(root,"work/props.json",output=True)

    def test_external_junction_and_internal_output_alias(self):
        if os.name!="nt": self.skipTest("Windows junction test")
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            root=Path(root)
            for name,target in (("external",Path(outside)),("alias",root/"input")):
                target.mkdir(exist_ok=True)
                link=root/name
                subprocess.run(["cmd","/c","mklink","/J",str(link),str(target)],check=True,capture_output=True)
                try:
                    if name=="external":
                        with self.assertRaisesRegex(ValueError,"escapes"): resolve_path(root,name+"/file")
                    with self.assertRaises(ValueError): resolve_path(root,name+"/file",output=True)
                finally:
                    link.rmdir()  # Remove only the junction, not its target.

    def test_duplicate_json_and_nonfinite(self):
        for data in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(ValueError): read_json(data)

    def test_shared_contract_invalid_cases(self):
        corpus=read_json((BASE/"fixtures/contracts-cases.json").read_bytes())
        for case in corpus:
            with self.subTest(name=case["name"]):
                if case["valid"]: validate(case["kind"],case["value"])
                else:
                    with self.assertRaises(ValueError): validate(case["kind"],case["value"])


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.board=create_fixture(self.root)
        self.shot=self.board["shots"][0]
        _,timings=compile_timing(self.board)
        self.clock=timings[0]
        self.render={"width":1920,"height":1080,"fps_num":30,"fps_den":1,"alpha_background":"#ffffff"}

    def png(self,image,**kwargs):
        buffer=BytesIO()
        image.save(buffer,format="PNG",**kwargs)
        return buffer.getvalue()

    def test_exif_bbox_all_orientations(self):
        expected=[[.1,.2,.4,.6],[.6,.2,.9,.6],[.6,.4,.9,.8],[.1,.4,.4,.8],
                  [.2,.1,.6,.4],[.4,.1,.8,.4],[.4,.6,.8,.9],[.2,.6,.6,.9]]
        for orientation,want in enumerate(expected,1):
            actual=orient_bbox([.1,.2,.4,.6],orientation)
            for a,b in zip(actual,want): self.assertAlmostEqual(a,b)
            exif=Image.Exif()
            exif[274]=orientation
            raw=self.png(Image.new("RGB",(80,40),"red"),exif=exif)
            encoded,_,report=prepare_image(raw,self.shot,self.render,self.clock)
            self.assertEqual(report["oriented_size"],[40,80] if orientation>=5 else [80,40])
            self.assertFalse(Image.open(BytesIO(encoded)).getexif())

    def test_alpha_icc_cover_and_preview(self):
        icc=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        raw=self.png(Image.new("RGBA",(100,200),(255,0,0,128)),icc_profile=icc)
        encoded,preview,report=prepare_image(raw,self.shot,self.render,self.clock)
        result=Image.open(BytesIO(encoded))
        self.assertEqual(result.mode,"RGB")
        self.assertEqual(result.size[0]*9,result.size[1]*16)
        self.assertEqual(result.getpixel((0,0)),(255,127,127))
        self.assertEqual(Image.open(BytesIO(preview)).size,(480,270))
        self.assertEqual(report["color"],"converted_to_sRGB")
        self.assertTrue(report["upscale_risk"])
        self.assertGreater(report["cover_box"][1],0)

    def test_bad_icc_and_animation_fail(self):
        with self.assertRaisesRegex(ValueError,"ICC"):
            prepare_image(self.png(Image.new("RGB",(10,10)),icc_profile=b"broken"),self.shot,self.render,self.clock)
        one=Image.new("RGB",(10,10),"red")
        buffer=BytesIO()
        one.save(buffer,format="PNG",save_all=True,append_images=[Image.new("RGB",(10,10),"blue")])
        with self.assertRaisesRegex(ValueError,"single-frame"):
            prepare_image(buffer.getvalue(),self.shot,self.render,self.clock)

    def test_subject_missing_and_clipped_localization(self):
        raw=(self.root/self.shot["image"]).read_bytes()
        self.shot["subject_bbox"]=None
        _,_,report=prepare_image(raw,self.shot,self.render,self.clock)
        self.assertEqual(report["subject_status"],"UNVERIFIED")
        self.shot["subject_bbox"]=[0,0,.2,.2]
        _,_,report=prepare_image(raw,self.shot,self.render,self.clock)
        self.assertEqual(report["subject_status"],"REVIEW_REQUIRED")
        self.assertEqual(report["clipped_global_frames"][0],0)
        approved_test_project(self.root)
        board=read(self.root,"input/storyboard.json")
        board["shots"][0]["subject_bbox"]=[0,0,.2,.2]
        save(self.root,"input/storyboard.json",board)
        from speech_support import seed_alignment
        seed_alignment(self.root)
        # P3A invalidates the visual approval before the later per-frame crop gate.
        with self.assertRaisesRegex(ValueError,"approved review geometry is missing or stale"): compile_project(self.root)


if __name__=="__main__":
    unittest.main()
