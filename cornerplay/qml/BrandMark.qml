import QtQuick

// The Cornerplay mark: the C with a play button in a rounded square, in the theme's colours.
// play() animates it in (splash, TV intro): the C swings round, the play button pops, the
// sparks flick on.
Item {
    id: bm
    property int size: 36
    property var theme: app.theme
    readonly property color accent: theme.primary  // the wallpaper's accent, grey included
    width: size; height: size

    function play() {
        if (app.light) return
        intro.stop()
        cLayer.rotation = -70; cLayer.opacity = 0
        tri.scale = 0; spark.opacity = 0; spark.pop = 0.6
        intro.start()
    }

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
        BrandLayer {
            id: cLayer
            anchors.fill: parent
            name: "mark-c"
            tint: bm.theme.dark === false ? "#f4ede4" : bm.theme.onSurface
        }
        BrandLayer {
            id: tri
            anchors.fill: parent
            name: "mark-tri"
            tint: bm.accent
            transformOrigin: Item.Center
        }
        BrandLayer {
            id: spark
            anchors.fill: parent
            name: "mark-spark"
            tint: bm.accent
            // grow out from the C's top right, where the sparks start
            transform: Scale { id: sparkScale; origin.x: spark.width * 0.7; origin.y: spark.height * 0.32; xScale: spark.pop; yScale: spark.pop }
            property real pop: 1
        }
    }

    SequentialAnimation {
        id: intro
        ParallelAnimation {
            NumberAnimation { target: cLayer; property: "rotation"; to: 0; duration: 620; easing.type: Easing.OutBack; easing.overshoot: 1.4 }
            NumberAnimation { target: cLayer; property: "opacity"; to: 1; duration: 300 }
            SequentialAnimation {
                PauseAnimation { duration: 260 }
                NumberAnimation { target: tri; property: "scale"; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
            }
        }
        // The sparks: on, a flicker, on for good.
        ParallelAnimation {
            NumberAnimation { target: spark; property: "pop"; to: 1; duration: 260; easing.type: Easing.OutBack }
            SequentialAnimation {
                NumberAnimation { target: spark; property: "opacity"; to: 1; duration: 90 }
                NumberAnimation { target: spark; property: "opacity"; to: 0.25; duration: 70 }
                NumberAnimation { target: spark; property: "opacity"; to: 1; duration: 110 }
            }
        }
    }
}
