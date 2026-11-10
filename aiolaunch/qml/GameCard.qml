import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// One cover tile in the library grid.
Item {
    id: card
    required property var theme
    required property bool current
    required property string key
    required property string store
    required property var covers
    required property string title
    required property string storeName
    required property string storeColor
    required property string cover
    required property string coverFallback
    required property bool installed
    required property string job
    required property real progress
    required property int copies
    required property bool update
    property int cornerRadius: 14
    property bool showBadge: true
    property bool showTitle: false
    property bool dim: true
    signal opened()
    signal activated()

    readonly property bool lit: hover.hovered || current

    Rectangle {
        id: frame
        anchors.fill: parent
        anchors.margins: 8
        radius: card.cornerRadius
        color: theme.surfaceContainerHigh
        scale: card.lit && !app.light ? 1.03 : 1.0
        Behavior on scale { enabled: !app.light; NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

        Item {
            id: art
            anchors.fill: parent
            layer.enabled: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
            layer.effect: MultiEffect {
                maskEnabled: true
                maskSource: mask
                maskThresholdMin: 0.5
                maskSpreadAtMin: 1.0
            }

            // Placeholder shown until (or instead of) a cover.
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.darker(card.storeColor, 2.2) }
                    GradientStop { position: 1; color: theme.surfaceContainerLowest || theme.surfaceContainerLow }
                }
                Text {
                    anchors.centerIn: parent
                    width: parent.width - 28
                    text: card.title
                    color: theme.onSurface
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    visible: img.status !== Image.Ready
                }
            }

            ArtImage {
                id: img
                anchors.fill: parent
                sources: card.covers
                sourceSize.width: app.light ? 280 : 400
                opacity: status === Image.Ready ? (card.installed || !card.dim ? 1 : 0.55) : 0
                Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 200 } }
            }

            // Title strip, on hover or when there is no art to read.
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 74
                opacity: (card.lit || card.showTitle) && img.status === Image.Ready ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: "#e6000000" }
                }
                Text {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 }
                    text: card.title
                    color: "white"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }

            // Install progress.
            Rectangle {
                visible: card.job !== ""
                anchors.fill: parent
                color: "#99000000"
                Column {
                    anchors.centerIn: parent
                    spacing: 10
                    width: parent.width - 36
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        color: "white"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        text: card.job === "uninstall" ? "Removing…"
                              : card.progress < 0 ? "Starting…"
                              : (card.job === "update" ? "Updating " : "Installing ") + Math.floor(card.progress) + "%"
                    }
                    Rectangle {
                        width: parent.width; height: 5; radius: 3
                        color: "#40ffffff"
                        Rectangle {
                            height: parent.height; radius: 3
                            color: theme.primary
                            width: parent.width * Math.max(0.04, card.progress / 100)
                            Behavior on width { NumberAnimation { duration: 300 } }
                        }
                    }
                }
            }
        }

        Rectangle { id: mask; anchors.fill: parent; radius: frame.radius; layer.enabled: true; visible: false }

        // Store chip.
        Rectangle {
            visible: card.showBadge
            x: 10; y: 10
            height: 22; radius: 11
            width: chip.implicitWidth + 31
            color: "#cc000000"
            StoreIcon { x: 7; anchors.verticalCenter: parent.verticalCenter; size: 12; store: card.store; color: card.storeColor }
            Text { id: chip; x: 23; anchors.verticalCenter: parent.verticalCenter; text: card.storeName + (card.copies > 1 ? "  +" + (card.copies - 1) : ""); color: "white"; font.pixelSize: 11 }
        }

        // Not-installed marker.
        Rectangle {
            visible: !card.installed && card.job === ""
            anchors { right: parent.right; top: parent.top; margins: 10 }
            width: 22; height: 22; radius: 11
            color: "#cc000000"
            Text { anchors.centerIn: parent; text: "↓"; color: "white"; font.pixelSize: 13; font.bold: true }
        }

        // Update-available marker.
        Rectangle {
            visible: card.installed && card.update && card.job === ""
            anchors { right: parent.right; top: parent.top; margins: 10 }
            width: 22; height: 22; radius: 11
            color: theme.primary
            Text { anchors.centerIn: parent; text: "↑"; color: theme.onPrimary; font.pixelSize: 13; font.bold: true }
        }

        Rectangle {
            anchors.fill: parent
            radius: frame.radius
            color: "transparent"
            border.width: card.lit ? 2 : 1
            border.color: card.lit ? theme.primary : theme.outlineVariant
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        onSingleTapped: card.opened()
        onDoubleTapped: card.activated()
    }
}
