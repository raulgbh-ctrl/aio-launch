import QtQuick

// The Cornerplay mark: the C with a play button in a rounded square, in the theme's colours.
Item {
    id: bm
    property int size: 36
    property var theme: app.theme
    // As in WordMark: the wallpaper's accent, or the logo's orange when it has no colour.
    readonly property color accent: theme.primary.hslSaturation > 0.18 ? theme.primary : "#ff9a3c"
    width: size; height: size
    Rectangle {
        id: tile
        anchors.fill: parent
        radius: bm.size * 0.23
        // Dark themes: a lifted surface. Light themes: a deep tile, so the cream C still reads.
        readonly property color base: bm.theme.dark === false ? Qt.darker(bm.accent, 3.2) : bm.theme.surfaceContainerHighest
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.lighter(tile.base, 1.18) }
            GradientStop { position: 1.0; color: Qt.tint(tile.base, Qt.alpha(bm.accent, 0.14)) }
        }
        border.width: Math.max(1, Math.round(bm.size / 64))
        border.color: Qt.alpha("white", 0.08)
    }
    Item {
        anchors.centerIn: parent
        width: bm.size * 0.9; height: width
        BrandLayer { anchors.fill: parent; name: "mark-c"; tint: bm.theme.dark === false ? "#f4ede4" : bm.theme.onSurface }
        BrandLayer { anchors.fill: parent; name: "mark-play"; tint: bm.accent }
    }
}
