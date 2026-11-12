import QtQuick
import QtQuick.Effects
import QtQuick.Shapes

// A little picture for an empty screen, drawn in the logo's soft, rounded strokes and in the
// theme's colours (so it follows the wallpaper). kind: "library" (nothing yet: a screen
// waiting with the mark on it), "list" (an empty list: a stack of cards and a plus) or
// "search" (nothing matches: a magnifier with sparks).
Item {
    id: es
    property string kind: "library"
    property var theme: app.theme
    readonly property color ink: Qt.alpha(theme.onSurfaceVariant, 0.55)
    readonly property color accent: theme.primary
    readonly property real line: 5
    implicitWidth: 240; implicitHeight: 160

    // The season's small touch (Seasonal.qml): snow, leaves, petals or fireflies.
    Seasonal { anchors.fill: parent; anchors.margins: -30; theme: es.theme; count: 10; z: 5 }
    // A soft pool of accent light behind the drawing.
    RectangularShadow {
        visible: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
        anchors.centerIn: parent
        width: 120; height: 80; radius: 40
        blur: 60
        color: Qt.alpha(es.accent, 0.16)
    }
    // The floor line all three scenes stand on.
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: Qt.alpha(es.ink, 0.6); strokeWidth: es.line; fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            startX: 46; startY: 146
            PathLine { x: 194; y: 146 }
        }
    }

    // --- nothing in the library yet: a screen with the mark, waiting
    Item {
        anchors.fill: parent
        visible: es.kind === "library"
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {  // the screen
                strokeColor: es.ink; strokeWidth: es.line; fillColor: Qt.alpha(es.theme.surfaceContainerHigh, 0.6)
                joinStyle: ShapePath.RoundJoin
                PathRectangle { x: 62; y: 18; width: 116; height: 82; radius: 18 }
            }
            ShapePath {  // its stand
                strokeColor: es.ink; strokeWidth: es.line; fillColor: "transparent"
                capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                startX: 120; startY: 102
                PathLine { x: 120; y: 128 }
                PathMove { x: 98; y: 130 }
                PathLine { x: 142; y: 130 }
            }
        }
        BrandMark { x: 120 - size / 2; y: 59 - size / 2; size: 46; theme: es.theme }
    }

    // --- an empty list: a stack of cards, and a plus to add one
    Item {
        anchors.fill: parent
        visible: es.kind === "list"
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Qt.alpha(es.ink, 0.5); strokeWidth: es.line - 1; fillColor: "transparent"
                PathRectangle { x: 104; y: 18; width: 62; height: 88; radius: 12 }
            }
            ShapePath {
                strokeColor: Qt.alpha(es.ink, 0.75); strokeWidth: es.line - 0.5; fillColor: Qt.alpha(es.theme.surfaceContainerHigh, 0.5)
                PathRectangle { x: 90; y: 28; width: 62; height: 88; radius: 12 }
            }
            ShapePath {
                strokeColor: es.ink; strokeWidth: es.line; fillColor: es.theme.surfaceContainerHigh
                PathRectangle { x: 76; y: 38; width: 62; height: 88; radius: 12 }
            }
            ShapePath {  // the plus, in the accent
                strokeColor: es.accent; strokeWidth: es.line + 1; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 107; startY: 68
                PathLine { x: 107; y: 96 }
                PathMove { x: 93; y: 82 }
                PathLine { x: 121; y: 82 }
            }
        }
    }

    // --- nothing matches: a magnifier, and the logo's sparks
    Item {
        anchors.fill: parent
        visible: es.kind === "search"
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {  // the lens
                strokeColor: es.ink; strokeWidth: es.line + 1; fillColor: Qt.alpha(es.theme.surfaceContainerHigh, 0.55)
                PathAngleArc { centerX: 108; centerY: 66; radiusX: 34; radiusY: 34; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {  // the handle
                strokeColor: es.ink; strokeWidth: es.line + 6; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 133; startY: 91
                PathLine { x: 154; y: 114 }
            }
            ShapePath {  // the sparks, like the logo's
                strokeColor: es.accent; strokeWidth: es.line; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 152; startY: 30
                PathLine { x: 160; y: 18 }
                PathMove { x: 160; y: 44 }
                PathLine { x: 174; y: 38 }
            }
            ShapePath {  // a small play button inside the lens
                strokeColor: "transparent"; fillColor: Qt.alpha(es.accent, 0.85)
                joinStyle: ShapePath.RoundJoin
                startX: 100; startY: 54
                PathLine { x: 121; y: 66 }
                PathLine { x: 100; y: 78 }
                PathLine { x: 100; y: 54 }
            }
        }
    }
}
