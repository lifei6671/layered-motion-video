/**
 * SC-M2 全局动态字卡轨。基于现有镜头画面之上透明叠加，仅占用批准的稳定帧窗口。
 * 文字及章节动画借鉴 video-talkcraft；非商业条款与 Required Notice 见 talkcraft-recipes.tsx。
 * 任何配方必须由 motion-card-registry.ts 的静态白名单分派，禁止外部 React/JS/CSS。
 */
import {AbsoluteFill, Sequence, useCurrentFrame} from 'remotion';
import type {Props} from './contracts.generated.js';
import {TalkcraftInkUnderline, TalkcraftNumberSlab} from './talkcraft-recipes.js';
import {motionCardOpacity, motionRecipe} from './motion-card-registry.js';

export type MotionCard = NonNullable<Props['motion_cards']>[number];
type ColorTheme = {background: string; foreground: string; accent: string; secondary: string};
const THEMES: Record<MotionCard['style'], ColorTheme> = {
  paper: {background: '#f7f1e6', foreground: '#261c1a', accent: '#b64830', secondary: '#665a52'},
  ink: {background: '#231d22', foreground: '#fdf4e7', accent: '#eaa64f', secondary: '#d4c5b6'},
  bright: {background: '#f8fbff', foreground: '#172849', accent: '#2165ba', secondary: '#40577f'},
};
const clamp = (n: number) => Math.max(0, Math.min(1, n));
const ease = (n: number) => 1 - (1 - clamp(n)) ** 3;

function ChapterVisual({card, colors}: {card: MotionCard; colors: ColorTheme}) {
  const frame = useCurrentFrame();
  const letters = Array.from(card.text).length;
  const size = Math.min(125, Math.max(60, Math.floor(1300 / Math.max(1, letters))));
  const reveal = ease((frame - 12) / 16);
  const line = ease((frame - 28) / 9);
  const enter = ease((frame - 5) / 12);
  return <AbsoluteFill style={{display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: colors.background, fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif',
    overflow: 'hidden'}}>
    <div style={{position: 'absolute', width: '100%', height: 16, top: 0, left: 0,
      background: colors.accent, transform: `translateX(${(enter - 1) * 100}%)`}} />
    <div style={{maxWidth: 1550, textAlign: 'center', color: colors.foreground}}>
      <div style={{fontSize: 29, fontWeight: 600, letterSpacing: 9, color: colors.accent,
        opacity: ease((frame - 8) / 12), marginBottom: 36}}>CHAPTER</div>
      <div style={{fontSize: size, fontWeight: 800, lineHeight: 1.2,
        clipPath: `inset(0 ${100 * (1 - reveal)}% 0 0)`, transform: `translateY(${16 * (1 - reveal)}px)`}}>
        {card.text}
      </div>
      <div style={{height: 9, margin: '36px auto 0', width: 180,
        background: colors.accent, transform: `scaleX(${line})`}} />
      {card.label && <div style={{marginTop: 26, fontSize: 36,
        color: colors.secondary, opacity: ease((frame - 35) / 10)}}>{card.label}</div>}
    </div>
  </AbsoluteFill>;
}

function UnderlineVisual({card, colors}: {card: MotionCard; colors: ColorTheme}) {
  const frame = useCurrentFrame();
  const letters = Array.from(card.text).length;
  const fontSize = Math.min(116, Math.max(58, Math.floor(1320 / Math.max(1, letters))));
  const textWidth = Math.min(1480, letters * fontSize * 1.1);
  const appear = ease((frame - 6) / 13);
  return <AbsoluteFill style={{display: 'flex', justifyContent: 'center', alignItems: 'center',
    background: colors.background, fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif'}}>
    <div style={{color: colors.foreground, display: 'flex', flexDirection: 'column',
      alignItems: 'center', opacity: appear, transform: `translateY(${(1 - appear) * 14}px)`}}>
      <div style={{fontWeight: 800, fontSize, lineHeight: 1.2, whiteSpace: 'nowrap'}}>{card.text}</div>
      <TalkcraftInkUnderline width={textWidth} y={26} thickness={15}
        seed={Array.from(card.id).reduce((acc, c) => acc + c.codePointAt(0)!, 0)}
        startFrame={16} durationFrames={12} color={colors.accent} />
      {card.label && <div style={{fontSize: 33, color: colors.secondary, marginTop: 34}}>{card.label}</div>}
    </div>
  </AbsoluteFill>;
}

/** 直接以局部帧驱动，首尾过渡不会改变时间轴总帧数。 */
export function MotionCardVisual({card}: {card: MotionCard}) {
  const frame = useCurrentFrame();
  motionRecipe(card.recipe);
  const duration = card.end_frame - card.start_frame;
  const opacity = motionCardOpacity(frame, duration);
  const colors = THEMES[card.style];
  return <AbsoluteFill data-motion-card={card.id} data-recipe={card.recipe}
    style={{pointerEvents: 'none', overflow: 'hidden', opacity}}>
    {card.recipe === 'talkcraft-number-slab'
      ? <TalkcraftNumberSlab number={card.text} label={card.label}
          accent={colors.accent} ink={colors.foreground} background={colors.background} />
      : card.recipe === 'talkcraft-ink-underline'
        ? <UnderlineVisual card={card} colors={colors} />
        : <ChapterVisual card={card} colors={colors} />}
  </AbsoluteFill>;
}

export function MotionCardTrack({cards}: {cards: MotionCard[]}) {
  if (cards.length === 0) return null;
  return <>{cards.map(card =>
    <Sequence name={card.id} key={card.id} from={card.start_frame}
      durationInFrames={card.end_frame - card.start_frame}>
      <MotionCardVisual card={card} />
    </Sequence>
  )}</>;
}
