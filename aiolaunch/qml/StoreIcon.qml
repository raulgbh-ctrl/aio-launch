import QtQuick

// A store's logo (aiolaunch/icons/<store>.svg, from Simple Icons) drawn in any colour.
// The SVG is recoloured as text, so it needs no GPU effect. A store without a logo gets a dot.
Item {
    id: icon
    property string store: ""
    property color color: "white"
    property int size: 14
    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    readonly property string svg: app.storeIcons[icon.store] || ""
    readonly property string hex: "#" + [icon.color.r, icon.color.g, icon.color.b]
                                  .map(v => Math.round(v * 255).toString(16).padStart(2, "0")).join("")

    Image {
        id: logo
        anchors.fill: parent
        visible: icon.svg !== ""
        source: icon.svg ? "data:image/svg+xml;utf8," + encodeURIComponent(icon.svg.replace('fill="#ffffff"', 'fill="' + icon.hex + '"')) : ""
        sourceSize: Qt.size(icon.size * 2, icon.size * 2)
        fillMode: Image.PreserveAspectFit
        smooth: true
    }
    Rectangle {
        visible: icon.svg === ""
        anchors.centerIn: parent
        width: Math.round(icon.size * 0.62); height: width; radius: width / 2
        color: icon.color
    }
}
