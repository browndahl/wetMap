import { CloudRain, Layers3, Play, Radio } from "lucide-react";
import { RADAR_SCALE } from "@wetmap/shared";

export default function DesignPage() {
  return (
    <main className="design-page">
      <header>
        <span className="eyebrow"><CloudRain size={16} /> WetMap system</span>
        <h1>Calm weather,<br />clear decisions.</h1>
        <p>Token- og komponentreference for web og fremtidige mobile klienter.</p>
        <a href="/">Tilbage til kortet</a>
      </header>
      <section aria-labelledby="colors"><h2 id="colors">Overflader</h2><div className="swatches"><span /><span /><span /></div></section>
      <section aria-labelledby="radar"><h2 id="radar">Radar · dBZ</h2><div className="radar-swatches">{RADAR_SCALE.map((entry) => <div key={entry.min} style={{ background: entry.color }}><span>{entry.label}</span></div>)}</div></section>
      <section aria-labelledby="controls"><h2 id="controls">Kontroller</h2><div className="component-row"><button className="play-button" aria-label="Afspil"><Play /></button><button className="mode-button"><Layers3 size={17} /> 3D-bygninger</button><span className="freshness"><Radio size={13} /> Opdateret</span></div></section>
      <section aria-labelledby="type"><h2 id="type">Typografi</h2><p className="type-xl">19:45</p><p className="type-body">Baseret på data fra DMI og efterfølgende bearbejdet</p></section>
    </main>
  );
}
