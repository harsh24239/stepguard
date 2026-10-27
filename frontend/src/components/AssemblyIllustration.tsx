import { useId } from 'react';
import Icon from './Icon';

export default function AssemblyIllustration() {
  const id = useId().replaceAll(':', '');
  return <div className="assembly-illustration">
    <div className="illustration-topline"><span><span className="small-cross">+</span> THE WORKBENCH, IN FOCUS</span><span className="illustration-label">Workflow illustration</span></div>
    <svg className="assembly-scene" viewBox="0 0 600 390" role="img" aria-label="Illustration of a plate and four pins with reference and placement guides. This is not a live inspection.">
      <defs>
        <linearGradient id={`${id}-plate`} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#f0f4ff"/><stop offset="1" stopColor="#aebfee"/></linearGradient>
        <linearGradient id={`${id}-pin`} x1="0" y1="0" x2="1" y2="0"><stop stopColor="#365de5"/><stop offset=".5" stopColor="#7599ff"/><stop offset="1" stopColor="#3656c8"/></linearGradient>
        <pattern id={`${id}-grid`} width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#2a3856" strokeWidth=".7"/></pattern>
      </defs>
      <rect width="600" height="390" fill={`url(#${id}-grid)`}/>
      <ellipse cx="302" cy="293" rx="210" ry="58" fill="#080f20" opacity=".7"/>
      <path d="M79 208 298 91 525 213 306 335Z" fill="none" stroke="#6078b5" strokeDasharray="4 7" opacity=".6" transform="translate(0 26)"/>
      <path d="M94 216 301 105 513 220 306 331 94 216Z" fill="#697da6"/>
      <path d="M94 200 301 89 513 204 306 315 94 200Z" fill={`url(#${id}-plate)`}/>
      <path d="M94 200v16l212 115v-16Z" fill="#7389b4"/><path d="m306 315 207-111v16L306 331Z" fill="#536b9d"/>
      <path d="m120 200 181-96 186 100-181 97Z" fill="none" stroke="#fff" strokeOpacity=".55"/>
      <g fill="none" stroke="#8da7eb" strokeWidth="1.2" strokeDasharray="4 5"><ellipse cx="300" cy="133" rx="32" ry="17"/><ellipse cx="171" cy="202" rx="32" ry="17"/><ellipse cx="430" cy="204" rx="32" ry="17"/><ellipse cx="303" cy="272" rx="32" ry="17"/></g>
      {[[300,133],[171,202],[430,204],[303,272]].map(([x,y], i) => <g key={i}>
        <ellipse cx={x} cy={y+3} rx="19" ry="10" fill="#667ca9" opacity=".4"/>
        <path d={`M${x-13} ${y-41}v40c0 10 26 10 26 0v-40Z`} fill={`url(#${id}-pin)`}/>
        <ellipse cx={x} cy={y-41} rx="13" ry="7" fill="#96b5ff"/><ellipse cx={x} cy={y-42} rx="7" ry="3.5" fill="#b9cfff"/>
        <path d={`M${x-7} ${y-36}v29`} stroke="#9cbbff" strokeWidth="2" opacity=".6"/>
      </g>)}
      <g stroke="#8ca7e7" fill="none"><path d="M171 164V96H88"/><path d="M430 164V110h80"/><path d="m307 288 40 53h115"/><circle cx="171" cy="164" r="3" fill="#c2d3ff"/><circle cx="430" cy="164" r="3" fill="#c2d3ff"/><circle cx="307" cy="288" r="3" fill="#c2d3ff"/></g>
      <g fill="#c0d1f1" fontFamily="ui-monospace, monospace" fontSize="10" letterSpacing="1"><text x="42" y="83">01 / PARTS</text><text x="460" y="97">02 / POSITION</text><text x="371" y="360">03 / REFERENCE</text></g>
      <g fill="none" stroke="#526b9a"><path d="M22 42V22h20M558 22h20v20M578 348v20h-20M42 368H22v-20"/></g>
    </svg>
    <div className="illustration-caption"><span className="illustration-caption-icon"><Icon name="layers" size={18}/></span><div><strong>A procedure. A clear view. A guarded check.</strong><span>Visible evidence keeps each step in context.</span></div><Icon name="crosshair" size={22}/></div>
  </div>;
}
