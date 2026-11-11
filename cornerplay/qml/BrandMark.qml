import QtQuick

// The Cornerplay mark: the C with a play button in a rounded square, in the theme's colours.
// play() animates it in (splash, TV intro): the C swings round, the play button pops, the
// sparks flick on. Animators, which run on Qt's render thread: the start-up animation stays
// smooth while the app is still busy loading the library on the main thread.
Item {
    id: bm
    property int size: 36
    property var theme: app.theme
    readonly property color accent: theme.primary  // the wallpaper's accent, grey included
    width: size; height: size

    readonly property alias playing: intro.running
    function play() {
        if (app.light) return
        intro.stop()
        cLayer.rotation = -70; cLayer.opacity = 0
        tri.scale = 0; spark.opacity = 0; sparkPivot.scale = 0.6
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
            objectName: "markC"
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
        // The sparks grow out from the C's top right (70 %, 32 %): this item is centred there,
        // so scaling it (a ScaleAnimator scales about the centre) scales the sparks from there.
        Item {
            id: sparkPivot
            width: parent.width * 1.4; height: parent.height * 0.64
            BrandLayer {
                id: spark
                width: sparkPivot.width / 1.4; height: sparkPivot.height / 0.64
                name: "mark-spark"
                tint: bm.accent
            }
        }
    }

    SequentialAnimation {
        id: intro
        ParallelAnimation {
            RotationAnimator { target: cLayer; from: -70; to: 0; duration: 620; easing.type: Easing.OutBack; easing.overshoot: 1.4 }
            OpacityAnimator { target: cLayer; from: 0; to: 1; duration: 300 }
            SequentialAnimation {
                PauseAnimation { duration: 260 }
                ScaleAnimator { target: tri; from: 0; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
            }
        }
        // The sparks: on, a flicker, on for good.
        ParallelAnimation {
            ScaleAnimator { target: sparkPivot; from: 0.6; to: 1; duration: 260; easing.type: Easing.OutBack }
            SequentialAnimation {
                OpacityAnimator { target: spark; from: 0; to: 1; duration: 90 }
                OpacityAnimator { target: spark; from: 1; to: 0.25; duration: 70 }
                OpacityAnimator { target: spark; from: 0.25; to: 1; duration: 110 }
            }
        }
    }
}
