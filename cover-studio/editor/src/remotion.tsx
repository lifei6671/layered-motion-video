import React,{useEffect,useState} from 'react';
import {registerRoot,Still,delayRender,continueRender,cancelRender} from 'remotion';
import {CoverArtwork} from './CoverArtwork';
import {prepareArtwork} from './fonts';
import {CoverDocument,newDocument} from './model';
type Props={document:CoverDocument;assetBase:string};
function RemotionCover(props:Props) {
  const [handle]=useState(()=>delayRender('等待封面字体与图片'));
  const [ready,setReady]=useState(false);
  useEffect(()=>{
    let active=true;
    prepareArtwork(props.document,props.assetBase).then(()=>{
      if(active)setReady(true);
    }).catch(cancelRender);
    return ()=>{active=false;};
  },[props.document,props.assetBase]);
  useEffect(()=>{if(ready)continueRender(handle);},[ready,handle]);
  return ready?<CoverArtwork {...props}/>:null;
}
registerRoot(()=> <Still id="CoverArtwork" component={RemotionCover} width={1920} height={1080}
  defaultProps={{document:newDocument(''),assetBase:''}}
  calculateMetadata={({props})=>({width:props.document.width,height:props.document.height})}/>);
