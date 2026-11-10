import QtQuick

// A line icon from cornerplay/icons/ui (Lucide, ISC licence) drawn in any colour.
Item {
    id: icon
    property string name: ""
    property color color: "white"
    property int size: 16
    implicitWidth: size
    implicitHeight: size
    width: size
    height: size
    visible: svg !== ""

    readonly property string svg: app.uiIcons[icon.name] || ""
    readonly property string hex: "#" + [icon.color.r, icon.color.g, icon.color.b]
                                  .map(v => Math.round(v * 255).toString(16).padStart(2, "0")).join("")
    Image {
        anchors.fill: parent
        source: icon.svg ? "data:image/svg+xml;utf8," + encodeURIComponent(icon.svg.replace(/currentColor/g, icon.hex)) : ""
        sourceSize: Qt.size(Math.ceil(icon.size * Math.max(2, Screen.devicePixelRatio)), Math.ceil(icon.size * Math.max(2, Screen.devicePixelRatio)))
        smooth: true
    }
}
