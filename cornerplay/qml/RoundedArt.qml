import QtQuick
import QtQuick.Effects

// Its children, cut to a rounded rectangle. (Qt's clip is always square, so a cover inside
// a rounded box pokes out at the corners.) Cheap enough to stay on in Light mode too.
Item {
    id: r
    property real radius: 12
    default property alias content: inner.data

    Item {
        id: inner
        anchors.fill: parent
        layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
        layer.effect: MultiEffect { maskEnabled: true; maskSource: shape; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
    }
    Rectangle { id: shape; anchors.fill: parent; radius: r.radius; layer.enabled: true; visible: false }
}
