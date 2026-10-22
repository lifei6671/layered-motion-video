/* Generated from ../../schemas/contracts.json. Do not edit. */

export type MotionType = 'static' | 'zoom_in' | 'zoom_out' | 'pan_x' | 'pan_y';
export type TransitionType = 'cut' | 'fade' | 'fade_black' | 'wipe_from_left' | 'wipe_from_right';
export type Placement = 'start_at_anchor' | 'end_at_anchor' | 'center_on_anchor';
export type Hash = string;
export type SourceMode = 'agent_generate' | 'third_party_retrieve' | 'manual_generate';
export type ImageStatus =
  | 'PLANNED'
  | 'WAITING_FOR_USER'
  | 'CANDIDATE_READY'
  | 'REVIEW_REQUIRED'
  | 'APPROVED'
  | 'REJECTED'
  | 'UNAVAILABLE';
export type ArtifactKind = 'production' | 'technical_fixture';

export interface StaticComicContracts {
  storyboard: Storyboard;
  render: Render;
  policy: Policy;
  manifest: Manifest;
  approvals: Approvals;
  overrides: Overrides;
  timeline: Timeline;
  props: Props;
  staging: Staging;
}
export interface Storyboard {
  schema_version: '2.0';
  episode_id: string;
  script_sha256: string;
  audio: Audio;
  /**
   * @minItems 1
   */
  shots: [Shot, ...Shot[]];
}
export interface Audio {
  source: string;
  sha256: string;
  sample_rate: 48000;
  duration_samples: number;
}
export interface Shot {
  id: string;
  image: string;
  /**
   * @minItems 2
   * @maxItems 2
   */
  script_range: [number, number];
  narrative: string;
  start_samples: number;
  boundary_reason: string;
  /**
   * @minItems 2
   * @maxItems 2
   */
  speech_interval_samples: [number, number];
  timing_source: 'acoustic_aligned' | 'manual_confirmed' | 'technical_fixture';
  motion: Motion;
  /**
   * @minItems 2
   * @maxItems 2
   */
  cover_anchor: [number, number];
  subject_bbox: [number, number, number, number] | null;
  transition_out: Transition | null;
}
export interface Motion {
  type: MotionType;
  scale_from: number;
  scale_to: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  crop_anchor_from: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  crop_anchor_to: [number, number];
  easing: 'smoothstep';
}
export interface Transition {
  to_shot_id: string;
  relation: string;
  evidence: string;
  visual_evidence: string;
  intent: string;
  type: TransitionType;
  duration_frames: number;
  placement: Placement;
  semantic_anchor_samples: number;
  planning_source: 'agent_reviewed' | 'human' | 'technical_fixture';
  /**
   * @minItems 2
   * @maxItems 2
   */
  image_hashes: [string, string];
  /**
   * @minItems 2
   * @maxItems 2
   */
  image_approval_hashes?: [Hash, Hash];
}
export interface Render {
  width: 1920;
  height: 1080;
  fps_num: 30;
  fps_den: 1;
  alpha_background: string;
}
export interface Policy {
  schema_version: '1.0';
  mode: 'agent_generate' | 'third_party_retrieve' | 'manual_generate' | 'mixed';
  status: 'SOURCE_POLICY_PENDING' | 'APPROVED';
  default_channel: string | null;
  /**
   * @minItems 0
   */
  allowed_channels: Assignment[];
  shots: {
    [k: string]: Assignment;
  };
  supersedes: string | null;
  confirmation: {
    human: Human;
    payload_sha256: string;
  } | null;
}
export interface Assignment {
  source_mode: SourceMode;
  channel: string;
}
export interface Human {
  actor: string;
  actor_role: 'human';
  at: string;
  evidence: string;
  confirmation?: {
    source: 'local_terminal' | 'conversation';
    scope: 'policy' | 'plan' | 'images' | 'transitions' | 'preview' | 'final';
    payload: {
      [k: string]: unknown;
    };
    conversation?: ConversationEvidence;
    signature: string;
  };
}
export interface ConversationEvidence {
  thread_id: string;
  message_id?: string;
  user_message: string;
  scope: 'policy' | 'plan' | 'images' | 'transitions' | 'preview' | 'final';
  decision_sha256: Hash;
}
export interface Manifest {
  schema_version: '1.0';
  /**
   * @minItems 0
   */
  assets: Asset[];
}
export interface Asset {
  shot_id: string;
  path: string;
  sha256: string;
  source_mode: SourceMode;
  channel: string;
  purpose: 'production' | 'reference_only' | 'technical_fixture';
  prompt: string;
  query: string;
  author: string;
  source_uri: string;
  accessed_at: string;
  download_method: string;
  style_version: string;
  license?: License;
  review_status: ImageStatus;
  reviewer: null | Human;
}
export interface License {
  id?: string;
  evidence?: string;
  usage_scope?: string;
  attribution?: string;
  publication_allowed?: boolean;
}
export interface Approvals {
  schema_version: '1.0';
  /**
   * @minItems 0
   */
  receipts: Receipt[];
}
export interface Receipt {
  shot_id: string;
  status: 'APPROVED' | 'REJECTED' | 'REVIEW_REQUIRED';
  image_sha256: string;
  asset_sha256: string;
  policy_sha256: string;
  human: Human;
  supply_sha256?: Hash;
}
export interface Overrides {
  schema_version: '1.0';
  script_sha256: string;
  audio_sha256: string;
  storyboard_sha256: string;
  /**
   * @minItems 0
   */
  entries: (
    | {
        kind: 'reading';
        /**
         * @minItems 2
         * @maxItems 2
         */
        script_range: [number, number];
        reading: string;
        reason: string;
        human: Human;
      }
    | {
        kind: 'window';
        /**
         * @minItems 2
         * @maxItems 2
         */
        script_range: [number, number];
        /**
         * @minItems 2
         * @maxItems 2
         */
        samples: [number, number];
        reason: string;
        human: Human;
      }
    | {
        kind: 'boundary';
        from_shot_id: string;
        to_shot_id: string;
        sample: number;
        reason: string;
        human: Human;
      }
    | {
        kind: 'asr_correction';
        /**
         * @minItems 2
         * @maxItems 2
         */
        script_range: [number, number];
        coarse_sha256: Hash;
        expected: string;
        recognized: string;
        reason: string;
        human: Human;
      }
  )[];
}
export interface Timeline {
  schema_version: '2.0';
  compiler_version: string;
  artifact_kind: ArtifactKind;
  episode_id: string;
  input_hashes: {
    [k: string]: string;
  };
  audio: Audio;
  video: Video;
  /**
   * @minItems 1
   */
  shots: [
    {
      source: Shot;
      execution: ExecutionShot;
    },
    ...{
      source: Shot;
      execution: ExecutionShot;
    }[]
  ];
}
export interface Video {
  width: 1920;
  height: 1080;
  fps_num: 30;
  fps_den: 1;
  total_frames: number;
}
export interface ExecutionShot {
  id: string;
  staged_image: string;
  image_sha256: string;
  start_frame: number;
  end_frame: number;
  sequence_start_frame: number;
  head_hold_frames: number;
  logical_frames: number;
  tail_hold_frames: number;
  physical_frames: number;
  motion: Motion;
  transition_out: CompiledTransition | null;
}
export interface CompiledTransition {
  type: TransitionType;
  duration_frames: number;
  placement: Placement;
  pre_frames: number;
  post_frames: number;
  semantic_anchor_samples: number;
  semantic_anchor_frame: number;
  transition_start_frame: number;
  transition_end_frame: number;
}
export interface Props {
  schema_version: '2.0';
  artifact_kind: ArtifactKind;
  video: Video;
  /**
   * @minItems 1
   */
  shots: [ExecutionShot, ...ExecutionShot[]];
}
export interface Staging {
  schema_version: '1.0';
  artifact_kind: ArtifactKind;
  policy_sha256: string;
  /**
   * @minItems 1
   */
  images: [
    {
      shot_id: string;
      source_sha256: string;
      asset_sha256: string;
      staged_image: string;
      staged_sha256: string;
    },
    ...{
      shot_id: string;
      source_sha256: string;
      asset_sha256: string;
      staged_image: string;
      staged_sha256: string;
    }[]
  ];
}
