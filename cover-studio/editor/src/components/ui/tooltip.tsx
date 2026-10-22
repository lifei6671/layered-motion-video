"use client"

import * as React from "react"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { cn } from "@/lib/utils"

const TooltipPortalHost = React.createContext<HTMLElement | null>(null)

function TooltipProvider({ children, ...props }: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  const [host, setHost] = React.useState<HTMLElement | null>(null)
  React.useEffect(() => {
    const updateHost = () => setHost(document.fullscreenElement as HTMLElement | null)
    updateHost()
    document.addEventListener("fullscreenchange", updateHost)
    return () => document.removeEventListener("fullscreenchange", updateHost)
  }, [])
  return <TooltipPortalHost.Provider value={host}><TooltipPrimitive.Provider {...props}>{children}</TooltipPrimitive.Provider></TooltipPortalHost.Provider>
}

const Tooltip = TooltipPrimitive.Root

const TooltipTrigger = TooltipPrimitive.Trigger

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, collisionPadding = 8, ...props }, ref) => (
  <TooltipPrimitive.Portal container={React.useContext(TooltipPortalHost) ?? undefined}>
    <TooltipPrimitive.Content
      ref={ref}
      data-slot="tooltip-content"
      sideOffset={sideOffset}
      collisionPadding={collisionPadding}
      className={cn(
        "ui-tooltip-content",
        className
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
))
TooltipContent.displayName = TooltipPrimitive.Content.displayName

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
