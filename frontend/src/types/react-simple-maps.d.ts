declare module 'react-simple-maps' {
  import { ReactNode, MouseEvent } from 'react';
  interface ComposableMapProps { projection?:string; style?:React.CSSProperties; projectionConfig?:Record<string,unknown>; children?:ReactNode; }
  interface ZoomableGroupProps { zoom?:number; center?:[number,number]; onMoveEnd?:(data:{coordinates:[number,number];zoom:number})=>void; minZoom?:number; maxZoom?:number; children?:ReactNode; }
  interface GeographiesProps { geography:string; children:(data:{geographies:Geography[]})=>ReactNode; }
  interface Geography { rsmKey:string; id:string|number; properties:Record<string,unknown>; }
  interface GeographyProps { key?:string; geography:Geography; style?:{default?:React.CSSProperties;hover?:React.CSSProperties;pressed?:React.CSSProperties}; onMouseEnter?:(e:MouseEvent)=>void; onMouseMove?:(e:MouseEvent)=>void; onMouseLeave?:(e:MouseEvent)=>void; onClick?:(e:MouseEvent)=>void; }
  export function ComposableMap(props:ComposableMapProps):JSX.Element;
  export function ZoomableGroup(props:ZoomableGroupProps):JSX.Element;
  export function Geographies(props:GeographiesProps):JSX.Element;
  export function Geography(props:GeographyProps):JSX.Element;
}
