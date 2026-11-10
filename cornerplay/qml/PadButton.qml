import QtQuick

// One controller button, drawn the way the connected pad labels it.
// button: the position SDL reports ("a" bottom, "b" right, "x" left, "y" top, "lb", "rb", "lt", "rt", "start");
// style: "xbox", "playstation" or "nintendo" (from pad.style).
Item {
    id: pb
    property string button: "a"
    property string style: "xbox"
    property int size: 26
    readonly property bool shoulder: ["lb", "rb", "lt", "rt", "start"].indexOf(button) !== -1
    implicitWidth: shoulder ? label.implicitWidth + size * 0.7 : size
    implicitHeight: size
    width: implicitWidth
    height: implicitHeight

    readonly property var xbox: ({ a: ["A", "#6dc04b"], b: ["B", "#e5574d"], x: ["X", "#3d8fea"], y: ["Y", "#f2c230"] })
    readonly property var nintendo: ({ a: "B", b: "A", x: "Y", y: "X" })   // by position: bottom is B on a Switch pad
    readonly property var psColour: ({ a: "#7fa9ec", b: "#ec6f6f", x: "#d58ad8", y: "#41c7a0" })
    readonly property var shoulders: ({
        xbox: { lb: "LB", rb: "RB", lt: "LT", rt: "RT", start: "☰" },
        playstation: { lb: "L1", rb: "R1", lt: "L2", rt: "R2", start: "OPTIONS" },
        nintendo: { lb: "L", rb: "R", lt: "ZL", rt: "ZR", start: "+" } })

    // PlayStation face symbols as SVG (cross, circle, square, triangle).
    function psSvg(b, c) {
        const s = 'fill="none" stroke="' + c + '" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"'
        const shape = b === "a" ? '<path d="M8 8 L16 16 M16 8 L8 16" ' + s + '/>'
                    : b === "b" ? '<circle cx="12" cy="12" r="5" ' + s + '/>'
                    : b === "x" ? '<rect x="7.5" y="7.5" width="9" height="9" ' + s + '/>'
                    : '<path d="M12 6.8 L17.2 15.8 L6.8 15.8 Z" ' + s + '/>'
        return "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' + shape + '</svg>')
    }

    Rectangle {
        anchors.fill: parent
        radius: pb.shoulder ? height * 0.32 : width / 2
        color: "#26262b"
        border.width: 1
        border.color: Qt.alpha("white", 0.18)
    }
    Text {
        id: label
        visible: pb.shoulder || pb.style !== "playstation"
        anchors.centerIn: parent
        font.pixelSize: pb.shoulder ? Math.round(pb.size * (pb.button === "start" && pb.style === "playstation" ? 0.34 : 0.46))
                                    : Math.round(pb.size * 0.56)
        font.weight: Font.Bold
        color: pb.shoulder || pb.style === "nintendo" ? "#ececf0" : pb.xbox[pb.button][1]
        text: pb.shoulder ? pb.shoulders[pb.style][pb.button]
              : pb.style === "nintendo" ? pb.nintendo[pb.button] : pb.xbox[pb.button][0]
    }
    Image {
        visible: !pb.shoulder && pb.style === "playstation"
        anchors.fill: parent
        source: visible ? pb.psSvg(pb.button, pb.psColour[pb.button]) : ""
        sourceSize: Qt.size(pb.size * 2, pb.size * 2)
    }
}
