import { X } from "lucide-react";

import type { AccentHue, Density, Prefs } from "../state/prefs";
import type { Theme } from "../state/theme";

type PreferencesPanelProps = {
  theme: Theme;
  prefs: Prefs;
  onClose: () => void;
  onSetTheme: (theme: Theme) => void;
  onSetDensity: (density: Density) => void;
  onSetAccent: (accent: AccentHue) => void;
};

const ACCENTS: { hue: AccentHue; label: string; color: string }[] = [
  { hue: 45, label: "Terracotta", color: "oklch(0.62 0.15 45)" },
  { hue: 250, label: "Indigo", color: "oklch(0.58 0.14 250)" },
  { hue: 160, label: "Teal", color: "oklch(0.58 0.12 160)" },
  { hue: 20, label: "Rosewood", color: "oklch(0.58 0.17 20)" }
];

const DENSITIES: Density[] = ["cozy", "compact", "dense"];

export function PreferencesPanel({
  theme,
  prefs,
  onClose,
  onSetTheme,
  onSetDensity,
  onSetAccent
}: PreferencesPanelProps) {
  return (
    <div className="twk" role="dialog" aria-label="Preferences">
      <div className="twk__hd">
        <b>Preferences</b>
        <button className="iconbtn" type="button" onClick={onClose} aria-label="Close">
          <X size={15} aria-hidden="true" />
        </button>
      </div>
      <div className="twk__body">
        <div className="twk__row">
          <div className="twk__lbl">Theme</div>
          <div className="twk__seg">
            <button type="button" aria-pressed={theme === "dark"} onClick={() => onSetTheme("dark")}>
              Dark
            </button>
            <button type="button" aria-pressed={theme === "light"} onClick={() => onSetTheme("light")}>
              Light
            </button>
          </div>
        </div>
        <div className="twk__row">
          <div className="twk__lbl">Density</div>
          <div className="twk__seg">
            {DENSITIES.map((density) => (
              <button
                key={density}
                type="button"
                aria-pressed={prefs.density === density}
                onClick={() => onSetDensity(density)}
              >
                {density.charAt(0).toUpperCase() + density.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="twk__row">
          <div className="twk__lbl">Accent</div>
          <div className="twk__sw">
            {ACCENTS.map((accent) => (
              <button
                key={accent.hue}
                type="button"
                aria-pressed={prefs.accentHue === accent.hue}
                style={{ background: accent.color }}
                title={accent.label}
                aria-label={accent.label}
                onClick={() => onSetAccent(accent.hue)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
