---
name: Cover Studio Light
colors:
  surface: '#faf9fd'
  surface-dim: '#dbd9dd'
  surface-bright: '#faf9fd'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f7'
  surface-container: '#efedf1'
  surface-container-high: '#e9e7eb'
  surface-container-highest: '#e3e2e6'
  on-surface: '#1a1b1e'
  on-surface-variant: '#434655'
  inverse-surface: '#2f3033'
  inverse-on-surface: '#f1f0f4'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#1d4ed8'
  on-secondary: '#ffffff'
  secondary-container: '#4069f2'
  on-secondary-container: '#fffbff'
  tertiary: '#0051b1'
  on-tertiary: '#ffffff'
  tertiary-container: '#0f69dc'
  on-tertiary-container: '#edf0ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#dce1ff'
  secondary-fixed-dim: '#b7c4ff'
  on-secondary-fixed: '#001551'
  on-secondary-fixed-variant: '#0039b5'
  tertiary-fixed: '#d8e2ff'
  tertiary-fixed-dim: '#adc6ff'
  on-tertiary-fixed: '#001a42'
  on-tertiary-fixed-variant: '#004395'
  background: '#faf9fd'
  on-background: '#1a1b1e'
  surface-variant: '#e3e2e6'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  caption:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.04em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-sm: 0.5rem
  gutter-lg: 1.5rem
  margin: 1.5rem
  margin-sm: 1rem
  margin-lg: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes a high-precision, distraction-free environment for professional video cover and thumbnail creation. Blending the utilitarian clarity of modern desktop software with the approachability of premium creative tools, it emphasizes content over interface.

### Personality & Values
- **Precision & Clarity:** Crisp layout boundaries, clean micro-interactions, and immaculate alignment.
- **Creativity-Enabling:** Neutral architectural framing ensures the creator's video assets and graphic artwork remain the visual heroes.
- **Fluid Efficiency:** Instant responsiveness, contextual floating panels, and friction-free manipulation.

### Design Movement
**Modern Creative Minimalist:** Pure white and soft gray surface stratification, hairline borders (1px), subtle ambient diffusion, and micro-radii that communicate precision without feeling clinical.

## Colors

The color palette maintains a strict separation between application scaffolding, interactive states, and the workspace canvas.

### Palette Architecture
- **Canvas Stage:** `#F1F3F5` acts as the neutral backdrop separating user artwork from the application chrome.
- **Application Shell & Surfaces:** `#FFFFFF` anchors elevated inspectors, dialogs, and primary ribbons, complemented by `#F8F9FB` on toolbars, side navigation docks, and secondary panels.
- **Brand & Active Accents:** `#2563EB` provides instantaneous feedback for primary actions, selected canvas elements, alignment guides, and focused handles. Hover interactions deepen to `#1D4ED8`.
- **Typographic Tones:** High-contrast graphite carbon (`#202124`) for headings, primary metrics, and active menu items. Subordinate UI copy, shortcut keycaps, and secondary metadata utilize `#6B7280`.
- **Structural Lines:** Structural 1px dividers, gridlines, and card boundaries use `#E5E7EB`.
- **Surface Elevation Tints:** `#F3F4F6` serves as subtle container fills, inactive input backgrounds, and hover fills on lists and grid tiles.

## Typography

Typography prioritizes high legibility at micro sizes typical in dense inspector panels, layer trees, and coordinate readouts.

- **Typeface Selection:** Inter handles all interface levels, backed by system fallbacks (`-apple-system`, `PingFang SC`, `Noto Sans SC`) for Chinese text rendering.
- **Display & Headings:** Used primarily in export sheets, template selection dialogs, and workspace headers with tight tracking (`-0.02em` to `-0.01em`).
- **Body & Controls:** Regular weights (400) for prose descriptions and project names; Medium weights (500) for all interactive labels, input field values, button text, and property tags.
- **Micro-Data:** Labels and property readouts (X/Y, W/H, rotation) use `label-sm` or `caption` with tabular figures enabled (`font-variant-numeric: tabular-nums`).

## Layout & Spacing

The workspace uses a full-viewport, docked-panel layout model typical of creative suites.

### Workspace Architecture
- **Top Command Bar:** Fixed height (48px or 52px), housing document state, zoom presets, global actions, and primary export CTA.
- **Left Tool Rail / Asset Drawer:** 64px collapsed icon rail expanding into a 280px drawer for templates, media uploads, elements, and layers.
- **Center Canvas Stage:** Fluid viewport dynamically resizing with panel states. Uses `gutter` (16px) margin around the zoomable canvas frame.
- **Right Property Inspector:** Fixed 280px or 320px column displaying contextual controls based on active canvas selection.

### Rhythmic Density
- **Micro-Spacing (`space-xs`, `space-sm`):** Control groupings, segmented pills, alignment tool clusters, and input stepper gaps.
- **Component Padding (`space-md`, `space-lg`):** Internal padding for floating toolbars, dialogs, property sections, and asset cards.
- **Reflow & Breakpoints:** Desktop first (≥1280px) for the complete multi-dock studio layout. Below 1024px, the inspector collapses into slide-over sheets and the tool dock toggles via a bottom sheet.

## Elevation & Depth

Visual hierarchy uses clean structural boundaries paired with ultra-diffused, ambient shadow diffusion to preserve lightness.

### Elevation Levels
- **Level 0 (Stage & Docks):** Flat `#F1F3F5` (canvas backdrop) and `#F8F9FB` (sidebars). Delineated solely by crisp `1px solid #E5E7EB` borders without drop shadows.
- **Level 1 (Panels & Cards):** `#FFFFFF` fill with `1px solid #E5E7EB` and subtle ambient diffusion: `0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.02)`.
- **Level 2 (Floating Canvases & Toolbars):** Floating canvas viewport and contextual canvas HUDs use: `0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.03)`.
- **Level 3 (Popovers, Menus & Dialogs):** High-elevation overlays utilize soft layering: `0 12px 24px -4px rgba(0, 0, 0, 0.08), 0 4px 8px -2px rgba(0, 0, 0, 0.02)`.

### Canvas Transformation Geometry
- **Selection Bounding Box:** 1.5px solid `#2563EB` frame surrounded by an outer 1px semi-transparent halo (`rgba(37, 99, 235, 0.15)`).
- **Transform Handles:** 8px × 8px white squares or circles with a `1.5px solid #2563EB` border and subtle `0 1px 2px rgba(0, 0, 0, 0.15)` drop shadow.
- **Smart Alignment Guides:** 1px dashed or solid `#2563EB` vectors accompanied by floating pill badges indicating real-time pixel distances.

## Shapes

The interface embraces a disciplined soft curvature (`roundedness: 1`), conveying modern digital craftsmanship without whimsical or bubbly traits.

### Radius Specifications
- **Micro-Controls (Buttons, Inputs, Badges, Tabs):** 4px (`0.25rem`) standard curvature to ensure crisp alignment in tight toolbar clusters.
- **Medium Containers (Cards, Asset Tiles, Floating HUDs):** 8px (`0.5rem`) for visual grouping.
- **Large Overlays (Modal Dialogs, Export Drawers):** 12px (`0.75rem`) balanced with ambient shadows.
- **Pill Exceptions:** Pure rounded-full pills (`9999px`) are strictly reserved for zoom percentage toggles, canvas tags, and status chips.

## Components

### Buttons
- **Primary:** Solid `#2563EB` fill, `#FFFFFF` text, 4px border radius. Hover: `#1D4ED8`. Active: scale 0.99.
- **Secondary / Outline:** `#FFFFFF` fill, 1px `#E5E7EB` border, `#202124` text. Hover: `#F3F4F6` background, `#D1D5DB` border.
- **Ghost / Icon Action:** Transparent background, `#6B7280` icon color. Hover: `#F3F4F6` fill, `#202124` icon color.
- **Dimensions:** 32px standard height for inspectors; 36px or 40px for global header actions.

### Canvas Element Handles & Selection
- Contextual selection outlines: `#2563EB` with precise anti-aliasing.
- Rotation handle: Extended anchor line (16px) topped with an 8px circular white node bordered in `#2563EB`.

### Input Fields & Steppers
- **Property Inputs (W/H/X/Y):** 28px height, `#FFFFFF` fill, 1px `#E5E7EB` border. Prefix label (e.g., "X", "W") in muted `#6B7280`. Focus: 1px `#2563EB` border with `0 0 0 2px rgba(37, 99, 235, 0.15)` ring.
- **Numeric Scrubbers:** Hover cursor changes to `ew-resize`. Dragging horizontally adjusts value with numeric readout tooltip.

### Chips & Segmented Controls
- **Segmented Control:** `#F3F4F6` track with 4px inner padding. Active segment switches to `#FFFFFF` with 4px border radius, subtle card shadow (`0 1px 2px rgba(0,0,0,0.06)`), and `#202124` active text.
- **Tag Chips:** `#F8F9FB` background, 1px `#E5E7EB` border, 11px font size, 20px height.

### Layers & List Items
- **Tree Rows:** 32px height, left-aligned drag handles, visibility (eye) and lock icons appearing on hover.
- **Hover State:** `#F8F9FB` fill.
- **Active / Selected Layer:** `#EFF6FF` background with `#2563EB` text and left accent indicator bar (2px width).

### Cards & Asset Tiles
- **Media & Template Cards:** 16:9 ratio containers with 8px radius, 1px `#E5E7EB` borders, and overflow hidden. Hover triggers a subtle scale preview with quick action overlays (e.g., "Use Template", "Insert").