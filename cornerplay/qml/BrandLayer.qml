import QtQuick
import QtQuick.Effects

// One part of the Cornerplay logo (art/brand/<name>-*.png), painted in any colour so the
// logo follows the theme (and with it the wallpaper). The shape is filled with `tint`; the
// light and dark layers on top keep the logo's soft, rounded bevel whatever the colour.
Item {
    id: bl
    property string name
    property color tint: "white"
    readonly property size px: Qt.size(Math.ceil(width * Math.max(2, Screen.devicePixelRatio)),
                                       Math.ceil(height * Math.max(2, Screen.devicePixelRatio)))
    readonly property bool gpu: GraphicsInfo.api !== GraphicsInfo.Software
    Image {
        id: shape
        anchors.fill: parent
        source: "../art/brand/" + bl.name + "-fill.png"
        sourceSize: bl.px
        smooth: true
        visible: false   // the mask for the GPU path below
    }
    // Without a GPU there is no masking: the shape comes already filled with the colour.
    Image {
        anchors.fill: parent
        visible: !bl.gpu
        source: bl.gpu ? "" : "image://brandtint/" + bl.name + "/" + bl.tint.toString().slice(-6)
        sourceSize: bl.px
        smooth: true
    }
    Rectangle {
        anchors.fill: parent
        visible: bl.gpu
        color: bl.tint
        layer.enabled: bl.gpu
        layer.effect: MultiEffect { maskEnabled: true; maskSource: shape; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
    }
    Image { anchors.fill: parent; source: "../art/brand/" + bl.name + "-dark.png"; sourceSize: bl.px; smooth: true }
    Image { anchors.fill: parent; source: "../art/brand/" + bl.name + "-light.png"; sourceSize: bl.px; smooth: true }
}
