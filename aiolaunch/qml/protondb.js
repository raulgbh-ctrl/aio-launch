.pragma library
// ProtonDB tiers: label and colour (ProtonDB's own colours).
var tiers = {
    platinum: { label: "Platinum", color: "#b4c7dc" },
    gold:     { label: "Gold",     color: "#cfb53b" },
    silver:   { label: "Silver",   color: "#a6a6a6" },
    bronze:   { label: "Bronze",   color: "#cd7f32" },
    borked:   { label: "Borked",   color: "#ff1919" }
}
function label(t) { return tiers[t] ? tiers[t].label : "" }
function color(t) { return tiers[t] ? tiers[t].color : "transparent" }
