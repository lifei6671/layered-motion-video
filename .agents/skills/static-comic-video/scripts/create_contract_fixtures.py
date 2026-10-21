"""Generate the shared Python/Ajv valid and invalid JSON corpus."""
import argparse
import copy
from pathlib import Path
import tempfile

from create_fixture import create_fixture
from static_comic.contracts import bytes_digest, canonical, digest
from static_comic.project import compile_project, load_project


def create_corpus():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        create_fixture(root)
        docs, _, _ = load_project(root)
        result = compile_project(root, technical_fixture=True, write=False)
        docs.update({kind:result[kind] for kind in ("timeline", "props", "staging")})
        docs["overrides"] = {"schema_version": "1.0", "script_sha256": docs["storyboard"]["script_sha256"],
                             "audio_sha256": docs["storyboard"]["audio"]["sha256"],
                             "storyboard_sha256": bytes_digest((root/"input/storyboard.json").read_bytes()), "entries": []}
        cases = [{"name": kind + "-valid", "kind": kind, "valid": True, "value": value} for kind,value in docs.items()]
        human = {"actor": "TEST ONLY", "actor_role": "human", "at": "2026-10-21T00:00:00Z",
                 "evidence": "Synthetic schema fixture, not an actual human approval"}
        policy = copy.deepcopy(docs["policy"])
        policy["status"] = "APPROVED"
        policy["confirmation"] = {"human": human,
                                  "payload_sha256": digest({k:v for k,v in policy.items() if k != "confirmation"})}
        manifest = copy.deepcopy(docs["manifest"])
        receipts = []
        for asset in manifest["assets"]:
            asset.update(purpose="production", review_status="APPROVED", reviewer=human)
            asset["license"]["publication_allowed"] = True
            receipts.append({"shot_id": asset["shot_id"], "status": "APPROVED", "image_sha256": asset["sha256"],
                             "asset_sha256": digest(asset), "policy_sha256": digest(policy), "human": human})
        for kind,value in (("policy",policy),("manifest",manifest),
                           ("approvals",{"schema_version":"1.0","receipts":receipts})):
            cases.append({"name":kind+"-synthetic-approved", "kind":kind,"valid":True,"value":value})
        bad = [
            ("storyboard",["shots",0,"motion","type"],"random"),
            ("storyboard",["shots",0,"transition_out","type"],"spin"),
            ("storyboard",["shots",0,"start_samples"],-1),
            ("storyboard",["shots",0,"script_range"],[0,1.5]),
            ("render",["fps_num"],24),
            ("render",["fps_den"],1.001),
            ("props",["shots",0,"staged_image"],"../input/script.txt"),
            ("props",["shots",0,"physical_frames"],1.5),
            ("policy",["mode"],"auto"),
            ("policy",["extra"],True),
            ("manifest",["assets",0,"path"],"input/picture.png"),
            ("manifest",["assets",0,"license","publication_allowed"],"yes"),
            ("overrides",["audio_sha256"],"stale"),
        ]
        for index,(kind,path,value) in enumerate(bad):
            changed=copy.deepcopy(docs[kind])
            node=changed
            for key in path[:-1]: node=node[key]
            node[path[-1]]=value
            cases.append({"name": f"invalid-{index}-{'/'.join(map(str,path))}", "kind":kind,"valid":False,"value":changed})
        return cases


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    output=Path(parser.parse_args().output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(canonical(create_corpus())+b"\n")
