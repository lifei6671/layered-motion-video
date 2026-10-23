import {useEffect, useState} from 'react';
import {Sequence, staticFile, useCurrentFrame, useDelayRender} from 'remotion';
import {BasicEmphasis, emphasisState, numberAt, type VisualEvent} from './emphasis-presets.js';
import {AdvancedEmphasis} from './emphasis-advanced.js';

function EventVisual({event}: {event: VisualEvent}) {
  const localFrame = useCurrentFrame();
  const state = emphasisState(event, localFrame);
  const {layout} = event;
  return <svg viewBox="0 0 1920 1080" width="100%" height="100%" data-emphasis={event.id}
    data-global-frame={event.start_frame + localFrame} style={{position: 'absolute', pointerEvents: 'none', overflow: 'visible'}}>
    <g opacity={state.opacity} transform={`translate(${layout.x * 1920 + layout.width * 960 + state.dx} ${layout.y * 1080 + layout.height * 540 + state.dy}) scale(${state.scale}) translate(${-layout.width * 960} ${-layout.height * 540})`}
      style={{filter: event.shadow_px ? `drop-shadow(0px 0px ${event.shadow_px}px ${event.stroke_color})` : undefined}}>
      <svg width={layout.width * 1920} height={layout.height * 1080} overflow="visible">
        {event.tier === 1 ? <BasicEmphasis event={event} localFrame={localFrame} /> :
          <AdvancedEmphasis event={event} localFrame={localFrame} />}
      </svg>
    </g>
  </svg>;
}

function LoadedEmphasis({events}: {events: VisualEvent[]}) {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender('Loading locked emphasis fonts'));
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let disposed = false;
    const fonts = [...new Map(events.map(event => [event.font_sha256, event])).values()];
    Promise.all(fonts.map(async event => {
      const family = 'emphasis-' + event.font_sha256;
      const font = new FontFace(family, `url("${staticFile(event.font_path)}")`);
      document.fonts.add(await font.load());
    })).then(() => {
      // Browser glyph metrics are the last boundary before pixels. Refuse a
      // mismatched planner box rather than silently shrink or crop the text.
      for (const event of events) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        const text = document.createElementNS(svg.namespaceURI, 'text') as SVGTextElement;
        const width = event.layout.width * 1920;
        const height = event.layout.height * 1080;
        svg.style.position = 'absolute'; svg.style.visibility = 'hidden';
        text.setAttribute('font-family', 'emphasis-' + event.font_sha256);
        text.setAttribute('font-size', String(event.layout.font_size));
        text.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:space', 'preserve');
        text.setAttribute('x', String(width / 2)); text.setAttribute('y', String(height / 2));
        text.setAttribute('text-anchor', 'middle'); text.setAttribute('dominant-baseline', 'central');
        if (event.preset === 'stagger_group') {
          text.style.fontKerning = 'none'; text.style.fontVariantLigatures = 'none';
        }
        svg.appendChild(text); document.body.appendChild(svg);
        const samples = event.preset === 'number_tick' ? new Set(Array.from({length: event.enter_frames + 1},
          (_, frame) => numberAt(event.text, frame / event.enter_frames))) : [event.text];
        try {
          for (const sample of samples) {
            text.textContent = sample;
            const bounds = text.getBBox();
            if (bounds.x < -1 || bounds.y < -1 || bounds.x + bounds.width > width + 1 || bounds.y + bounds.height > height + 1) {
              throw new Error(event.id + ': loaded font glyphs exceed locked layout ' + JSON.stringify({
                bounds: {x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height}, width, height}));
            }
          }
        } finally {
          svg.remove();
        }
      }
      if (!disposed) setLoaded(true);
      continueRender(handle);
    }).catch(error => cancelRender(error));
    return () => { disposed = true; };
  }, [events, handle, continueRender, cancelRender]);
  if (!loaded) return null;
  return <>{events.map(event => <Sequence key={event.id} from={event.start_frame}
    durationInFrames={event.end_frame - event.start_frame} name={event.id}>
    <EventVisual event={event} />
  </Sequence>)}</>;
}

export function VisualEmphasisOverlay({events}: {events: VisualEvent[]}) {
  if (!events.length) return null;
  return <LoadedEmphasis events={events} />;
}
