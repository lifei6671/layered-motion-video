import React from 'react';
import {type Icon,Minus,Plus} from '@phosphor-icons/react';
import {Tooltip,TooltipTrigger,TooltipContent} from './ui/tooltip';
import {Slider} from './ui/slider';
import {InputGroup,InputGroupInput,InputGroupAddon,InputGroupButton} from './ui/input-group';
export function Hint({content,children,side='top',disabled=false}:{content:React.ReactNode;children:React.ReactElement;side?:React.ComponentProps<typeof TooltipContent>['side'];disabled?:boolean}) {
  return <Tooltip><TooltipTrigger asChild>{disabled?<span className="disabled-tooltip-trigger" tabIndex={0}>{children}</span>:children}</TooltipTrigger><TooltipContent side={side}>{content}</TooltipContent></Tooltip>;
}
export function IconButton({icon:Icon,label,active=false,disabled,...props}:React.ButtonHTMLAttributes<HTMLButtonElement>&{icon:Icon;label:string;active?:boolean}) {
  return <Hint content={label} disabled={disabled}><button type="button" className={'icon-button'+(active?' active':'')} aria-label={label} aria-pressed={active} disabled={disabled} {...props}><Icon size={19}/></button></Hint>;
}
export function NumberField({label,value,onChange,min=-16384,max=16384,step=1,suffix='',disabled=false}:{label:string;value:number;onChange:(v:number)=>void;min?:number;max?:number;step?:number;suffix?:string;disabled?:boolean}) {
  const [draft,setDraft]=React.useState(String(Math.round(value*100)/100));
  const id=React.useId();
  React.useEffect(()=>{setDraft(String(Math.round(value*100)/100));},[value]);
  const inputProps={id,'aria-label':label,type:'number',min,max,step,value:draft,disabled,
    onChange:(e:React.ChangeEvent<HTMLInputElement>)=>{setDraft(e.target.value);if(e.target.value!==''&&e.target.validity.valid)onChange(Number(e.target.value));},
    onBlur:()=>setDraft(String(Math.round(value*100)/100))};
  if(suffix==='%')return <div className="number-control percentage-control"><label className="number-field" htmlFor={id}><span>{label}</span><input {...inputProps}/><small>%</small></label><Slider aria-label={label+'滑块'} min={min} max={max} step={step} value={[Math.max(min,Math.min(max,value))]} disabled={disabled} onValueChange={([next])=>onChange(next)}/></div>;
  const stepValue=(direction:number)=>onChange(Math.round(Math.max(min,Math.min(max,value+direction*step))*100000)/100000);
  return <div className="number-control stepper-control"><label htmlFor={id} className="number-caption">{label}{suffix&&<small>{suffix}</small>}</label><InputGroup className="number-stepper" data-disabled={disabled||undefined}>
    <InputGroupAddon align="inline-start"><Hint content={'减小'+label} disabled={disabled||value<=min}><InputGroupButton size="icon-xs" aria-label={'减小'+label} disabled={disabled||value<=min} onClick={()=>stepValue(-1)}><Minus data-icon="inline-start"/></InputGroupButton></Hint></InputGroupAddon>
    <InputGroupInput {...inputProps}/>
    <InputGroupAddon align="inline-end"><Hint content={'增大'+label} disabled={disabled||value>=max}><InputGroupButton size="icon-xs" aria-label={'增大'+label} disabled={disabled||value>=max} onClick={()=>stepValue(1)}><Plus data-icon="inline-end"/></InputGroupButton></Hint></InputGroupAddon>
  </InputGroup></div>;
}
export function ColorField({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}) {
  return <label className="color-field"><input type="color" aria-label={label} value={value} onChange={e=>onChange(e.target.value)}/><span>{label}</span><code>{value.toUpperCase()}</code></label>;
}
export function Section({title,children,collapsible=false,open=false}:{title:string;children:React.ReactNode;collapsible?:boolean;open?:boolean}) {
  return collapsible?<details className="property-section" open={open||undefined}><summary>{title}</summary><div className="section-body">{children}</div></details>:
    <section className="property-section"><h3>{title}</h3>{children}</section>;
}
