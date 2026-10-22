import * as React from "react"
import * as SliderPrimitive from "@radix-ui/react-slider"

import { cn } from "@/lib/utils"

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    data-slot="slider"
    className={cn(
      "ui-slider",
      className
    )}
    {...props}
  >
    <SliderPrimitive.Track data-slot="slider-track" className="ui-slider-track">
      <SliderPrimitive.Range data-slot="slider-range" className="ui-slider-range" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb data-slot="slider-thumb" className="ui-slider-thumb" aria-label={props['aria-label']} />
  </SliderPrimitive.Root>
))
Slider.displayName = SliderPrimitive.Root.displayName

export { Slider }
