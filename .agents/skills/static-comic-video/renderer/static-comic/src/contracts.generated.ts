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
export type ShotId = string;

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
  emphasisPolicy?: EmphasisPolicy;
  emphasisPlan?: EmphasisPlan;
  shotEmphasisDecision?: ShotEmphasisDecision;
  visualEmphasisEvent?: VisualEmphasisEvent;
  sfxEvent?: SfxEvent;
  fontManifest?: FontManifest;
  sfxManifest?: SfxManifest;
  compiledVisualEmphasis?: CompiledVisualEmphasis;
  compiledSfxEvent?: CompiledSfxEvent;
  emphasisResourceDecision?: EmphasisResourceDecision;
  emphasisResourceApprovals?: EmphasisResourceApprovals;
  motionPlan?: MotionPlan;
  motionCardEvent?: MotionCardEvent;
  compiledMotionCard?: CompiledMotionCard;
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
    scope: 'policy' | 'plan' | 'images' | 'transitions' | 'preview' | 'final' | 'resources';
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
  scope: 'policy' | 'plan' | 'images' | 'transitions' | 'preview' | 'final' | 'resources';
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
  /**
   * @maxItems 10000
   */
  visual_emphasis?: CompiledVisualEmphasis[];
  /**
   * @maxItems 100
   */
  motion_cards?: CompiledMotionCard[];
}
export interface CompiledVisualEmphasis {
  id: string;
  shot_id: ShotId;
  text: string;
  preset:
    | 'soft_rise'
    | 'comic_pop'
    | 'comic_burst'
    | 'number_tick'
    | 'underline_reveal'
    | 'stagger_group'
    | 'ink_reveal'
    | 'light_sweep'
    | 'fragment_disperse'
    | 'particle_assemble';
  tier: number;
  start_frame: number;
  end_frame: number;
  anchor_frame: number;
  enter_frames: number;
  hold_frames: number;
  exit_frames: number;
  markers: {
    enter_start: number;
    impact: number;
    settle: number;
    exit_start: number;
  };
  layout: {
    x: number;
    y: number;
    width: number;
    height: number;
    font_size: number;
  };
  font_asset_id: string;
  font_path: string;
  font_sha256: Hash;
  color: string;
  stroke_color: string;
  stroke_width: number;
  shadow_px: number;
  seed: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  script_range: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  speech_samples: [number, number];
}
export interface CompiledMotionCard {
  id: string;
  shot_id: ShotId;
  recipe: 'talkcraft-number-slab' | 'talkcraft-ink-underline' | 'talkcraft-chapter-card';
  /**
   * @minItems 2
   * @maxItems 2
   */
  script_range: [number, number];
  text: string;
  label?: string;
  style: 'paper' | 'ink' | 'bright';
  source: 'manual' | 'agent' | 'rules';
  start_frame: number;
  end_frame: number;
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
  /**
   * @maxItems 10000
   */
  resources?: {
    path: string;
    sha256: Hash;
    asset_id: string;
    kind: 'font' | 'effect';
  }[];
}
export interface EmphasisPolicy {
  schema_version: '1.0';
  mode: 'disabled' | 'auto' | 'manual' | 'mixed';
  visual: {
    enabled: boolean;
    selection?: 'adaptive' | 'manual';
    theme?: 'comic' | 'comic_bright' | 'comic_ink' | 'minimal' | 'cinematic';
    max_events_per_minute?: number;
    max_events_per_shot?: number;
    min_gap_frames?: number;
    max_concurrent?: 1;
    allow_advanced?: boolean;
    allow_prerender?: false;
    /**
     * @minItems 4
     * @maxItems 4
     */
    safe_insets?: [number, number, number, number];
  };
  audio: {
    enabled: boolean;
    /**
     * @maxItems 4
     */
    uses?:
      | []
      | ['keyword' | 'scene' | 'transition' | 'narrative']
      | ['keyword' | 'scene' | 'transition' | 'narrative', 'keyword' | 'scene' | 'transition' | 'narrative']
      | [
          'keyword' | 'scene' | 'transition' | 'narrative',
          'keyword' | 'scene' | 'transition' | 'narrative',
          'keyword' | 'scene' | 'transition' | 'narrative'
        ]
      | [
          'keyword' | 'scene' | 'transition' | 'narrative',
          'keyword' | 'scene' | 'transition' | 'narrative',
          'keyword' | 'scene' | 'transition' | 'narrative',
          'keyword' | 'scene' | 'transition' | 'narrative'
        ];
    max_events_per_minute?: number;
    max_concurrent?: number;
    default_sfx_gain_db?: number;
    peak_ceiling_dbfs?: number;
    sample_rate?: 48000;
    channels?: 2;
    sfx_peak_ceiling_dbfs?: number;
  };
}
export interface EmphasisPlan {
  schema_version: '1.0';
  script_sha256: Hash;
  /**
   * @maxItems 10000
   */
  shot_decisions: ShotEmphasisDecision[];
  /**
   * @maxItems 10000
   */
  visual_events: VisualEmphasisEvent[];
  /**
   * @maxItems 10000
   */
  audio_events: SfxEvent[];
  /**
   * @maxItems 10000
   */
  excluded: {
    id: string;
    reason_code:
      | 'VISUAL_BUSY'
      | 'EMBEDDED_TEXT'
      | 'NO_SAFE_REGION'
      | 'LOW_SEMANTIC_VALUE'
      | 'QUIET_NARRATIVE'
      | 'SCENE_MOTION_CONFLICT'
      | 'TIMING_UNCERTAIN'
      | 'DENSITY_BUDGET'
      | 'MANUAL_SKIP'
      | 'KEY_NUMBER'
      | 'KEY_CONCEPT'
      | 'NARRATIVE_EMPHASIS'
      | 'SCENE_CONTEXT'
      | 'TRANSITION_CONTEXT'
      | 'MANUAL_OVERRIDE'
      | 'DISABLED';
    reason: string;
  }[];
}
export interface ShotEmphasisDecision {
  shot_id: ShotId;
  text_decision: 'auto' | 'show' | 'skip';
  sfx_decision: 'auto' | 'allow' | 'silence';
  reason_code:
    | 'VISUAL_BUSY'
    | 'EMBEDDED_TEXT'
    | 'NO_SAFE_REGION'
    | 'LOW_SEMANTIC_VALUE'
    | 'QUIET_NARRATIVE'
    | 'SCENE_MOTION_CONFLICT'
    | 'TIMING_UNCERTAIN'
    | 'DENSITY_BUDGET'
    | 'MANUAL_SKIP'
    | 'KEY_NUMBER'
    | 'KEY_CONCEPT'
    | 'NARRATIVE_EMPHASIS'
    | 'SCENE_CONTEXT'
    | 'TRANSITION_CONTEXT'
    | 'MANUAL_OVERRIDE'
    | 'DISABLED';
  reason: string;
  text_reason_code?:
    | 'VISUAL_BUSY'
    | 'EMBEDDED_TEXT'
    | 'NO_SAFE_REGION'
    | 'LOW_SEMANTIC_VALUE'
    | 'QUIET_NARRATIVE'
    | 'SCENE_MOTION_CONFLICT'
    | 'TIMING_UNCERTAIN'
    | 'DENSITY_BUDGET'
    | 'MANUAL_SKIP'
    | 'KEY_NUMBER'
    | 'KEY_CONCEPT'
    | 'NARRATIVE_EMPHASIS'
    | 'SCENE_CONTEXT'
    | 'TRANSITION_CONTEXT'
    | 'MANUAL_OVERRIDE'
    | 'DISABLED';
  text_reason?: string;
  sfx_reason_code?:
    | 'VISUAL_BUSY'
    | 'EMBEDDED_TEXT'
    | 'NO_SAFE_REGION'
    | 'LOW_SEMANTIC_VALUE'
    | 'QUIET_NARRATIVE'
    | 'SCENE_MOTION_CONFLICT'
    | 'TIMING_UNCERTAIN'
    | 'DENSITY_BUDGET'
    | 'MANUAL_SKIP'
    | 'KEY_NUMBER'
    | 'KEY_CONCEPT'
    | 'NARRATIVE_EMPHASIS'
    | 'SCENE_CONTEXT'
    | 'TRANSITION_CONTEXT'
    | 'MANUAL_OVERRIDE'
    | 'DISABLED';
  sfx_reason?: string;
}
export interface VisualEmphasisEvent {
  id: string;
  shot_id: ShotId;
  /**
   * @minItems 2
   * @maxItems 2
   */
  script_range: [number, number];
  text: string;
  semantic_type: 'impact' | 'number' | 'concept' | 'narrative' | 'contrast' | 'sequence';
  importance: 'low' | 'medium' | 'high';
  preset:
    | 'soft_rise'
    | 'comic_pop'
    | 'comic_burst'
    | 'number_tick'
    | 'underline_reveal'
    | 'stagger_group'
    | 'ink_reveal'
    | 'light_sweep'
    | 'fragment_disperse'
    | 'particle_assemble';
  tier: number;
  layout: {
    preset: 'upper_left' | 'upper_right' | 'left_center' | 'right_center' | 'lower_side';
    x?: number;
    y?: number;
    max_width?: number;
  };
  pinned: boolean;
  source: 'agent' | 'rules' | 'human';
  font_asset_id?: string;
  font_size?: number;
  color?: string;
  stroke_color?: string;
  stroke_width?: number;
  shadow_px?: number;
  enter_frames?: number;
  hold_frames?: number;
  exit_frames?: number;
}
export interface SfxEvent {
  id: string;
  kind: 'keyword' | 'scene' | 'transition' | 'narrative';
  sfx_asset_id: string;
  anchor:
    | {
        type: 'visual_marker';
        visual_event_id: string;
        marker: 'enter_start' | 'impact' | 'settle' | 'exit_start';
        offset_samples: number;
      }
    | {
        type: 'shot_start';
        shot_id: ShotId;
        offset_samples: number;
      }
    | {
        type: 'speech_start';
        shot_id: ShotId;
        /**
         * @minItems 2
         * @maxItems 2
         */
        script_range: [number, number];
        offset_samples: number;
      }
    | {
        type: 'transition_frame';
        from_shot_id: ShotId;
        point: 'start' | 'mid' | 'end';
        offset_samples: number;
      }
    | {
        type: 'motion_marker';
        motion_card_id: string;
        marker: 'enter' | 'impact' | 'exit';
        offset_samples: number;
      };
  gain_db: number;
  fade_in_samples: number;
  fade_out_samples: number;
  pinned: boolean;
  source: 'agent' | 'rules' | 'human';
  trim_start_sample?: number;
  trim_end_sample?: number;
  allow_tail_trim?: boolean;
  sync_to?: 'onset' | 'peak' | 'end';
}
export interface FontManifest {
  schema_version: '1.0';
  /**
   * @maxItems 1000
   */
  assets: {
    asset_id: string;
    path: string;
    sha256: Hash;
    source_kind: 'local_created' | 'user_provided' | 'licensed_third_party' | 'confirmed_generated';
    source_uri: string;
    author: string;
    license: string;
    usage_scope: string;
    license_evidence: {
      path: string;
      sha256: Hash;
    };
    review_status: 'APPROVED' | 'TECHNICAL_ONLY' | 'CANDIDATE' | 'REJECTED';
    family: string;
  }[];
}
export interface SfxManifest {
  schema_version: '1.0';
  /**
   * @maxItems 10000
   */
  assets: {
    asset_id: string;
    path: string;
    sha256: Hash;
    source_kind: 'local_created' | 'user_provided' | 'licensed_third_party' | 'confirmed_generated';
    source_uri: string;
    author: string;
    license: string;
    usage_scope: string;
    license_evidence: {
      path: string;
      sha256: Hash;
    };
    review_status: 'APPROVED' | 'TECHNICAL_ONLY' | 'CANDIDATE' | 'REJECTED';
    sample_rate: number;
    channels: number;
    duration_samples: number;
    /**
     * @minItems 1
     */
    tags: ['keyword' | 'scene' | 'transition' | 'narrative', ...('keyword' | 'scene' | 'transition' | 'narrative')[]];
    normalized_path?: string;
    normalized_sha256?: Hash;
    generator?: {
      provider: 'earshot';
      bank_id: string;
      bank_version: string;
      source_commit: string;
      options_sha256: Hash;
    };
    cue_points?: {
      onset_samples: number;
      peak_samples: number;
      end_samples: number;
    };
  }[];
}
export interface CompiledSfxEvent {
  id: string;
  kind: 'keyword' | 'scene' | 'transition' | 'narrative';
  start_sample: number;
  gain_db: number;
  fade_in_samples: number;
  fade_out_samples: number;
  asset_id: string;
  asset_sha256: Hash;
  source_trim_samples: number;
  play_samples: number;
  normalized_path: string;
  normalized_sha256: Hash;
  pinned?: boolean;
  source?: 'agent' | 'rules' | 'human';
  anchor?:
    | {
        type: 'visual_marker';
        visual_event_id: string;
        marker: 'enter_start' | 'impact' | 'settle' | 'exit_start';
        offset_samples: number;
      }
    | {
        type: 'shot_start';
        shot_id: ShotId;
        offset_samples: number;
      }
    | {
        type: 'speech_start';
        shot_id: ShotId;
        /**
         * @minItems 2
         * @maxItems 2
         */
        script_range: [number, number];
        offset_samples: number;
      }
    | {
        type: 'transition_frame';
        from_shot_id: ShotId;
        point: 'start' | 'mid' | 'end';
        offset_samples: number;
      }
    | {
        type: 'motion_marker';
        motion_card_id: string;
        marker: 'enter' | 'impact' | 'exit';
        offset_samples: number;
      };
  allow_tail_trim?: boolean;
  sync_to?: 'onset' | 'peak' | 'end';
  motion_frame?: number;
}
export interface EmphasisResourceDecision {
  schema_version: '1.0';
  asset_kind: 'font' | 'sfx';
  asset_id: string;
  asset_sha256: Hash;
  asset_manifest_sha256: Hash;
  decision: 'APPROVED' | 'REJECTED';
  human: Human;
}
export interface EmphasisResourceApprovals {
  schema_version: '1.0';
  /**
   * @maxItems 1000
   */
  decisions: EmphasisResourceDecision[];
}
export interface MotionPlan {
  schema_version: '1.0';
  script_sha256: Hash;
  /**
   * @maxItems 1000
   */
  events: MotionCardEvent[];
}
export interface MotionCardEvent {
  id: string;
  shot_id: ShotId;
  recipe: 'talkcraft-number-slab' | 'talkcraft-ink-underline' | 'talkcraft-chapter-card';
  /**
   * @minItems 2
   * @maxItems 2
   */
  script_range: [number, number];
  text: string;
  label?: string;
  style: 'paper' | 'ink' | 'bright';
  source: 'manual' | 'agent' | 'rules';
  start_frame: number;
  end_frame: number;
}
