import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import "protondb.js" as ProtonDB

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
    required property string protondb
    property bool showProtonDb: true
    property int cornerRadius: 14
    property bool showBadge: true
    property bool showTitle: false
    property bool dim: true
    signal opened()
    signal activated()

    readonly property bool hovered: hover.hovered
    readonly property bool lit: hover.hovered || current

    // Accent glow around the pointed-at card: a few fading outlines, cheap on any GPU.
    Item {
        anchors.fill: frame
        scale: frame.scale
        visible: card.lit
        opacity: card.lit ? 1 : 0
        Repeater {
            model: 5
            Rectangle {
                required property int index
                anchors.fill: parent
                anchors.margins: -(index + 1) * 2
                anchors.topMargin: -(index + 1) * 2 + 4  // sits a little low, like a shadow
                radius: card.cornerRadius + (index + 1) * 2
                color: "transparent"
                border.width: 2
                border.color: Qt.alpha(card.theme.primary, 0.30 - index * 0.055)
            }
        }
    }

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
                // Shimmer while the cover downloads.
                Rectangle {
                    id: shimmer
                    visible: img.status === Image.Loading && !app.light
                    width: parent.width * 0.6
                    height: parent.height
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 0.5; color: Qt.alpha("white", 0.09) }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                    NumberAnimation on x {
                        running: shimmer.visible
                        loops: Animation.Infinite
                        from: -shimmer.width; to: card.width
                        duration: 1300
                        easing.type: Easing.InOutQuad
                    }
                }
            }

            // Only wide art for this game: show all of it, centred, over a blurred, enlarged
            // copy that fills the card (rather than cropping a slice out of the middle).
            readonly property bool wideArt: img.status === Image.Ready && img.implicitWidth > img.implicitHeight * 1.1
            Image {
                id: wideBack
                anchors.fill: parent
                visible: false
                source: parent.wideArt ? img.source : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                sourceSize.width: 160
            }
            MultiEffect {
                anchors.fill: parent
                source: wideBack
                visible: parent.wideArt && !app.light && wideBack.status === Image.Ready
                blurEnabled: true; blur: 1.0; blurMax: 48
                brightness: -0.15
                opacity: img.opacity
            }
            ArtImage {
                id: img
                anchors.fill: parent
                sources: card.covers
                fillMode: parent.wideArt ? Image.PreserveAspectFit : Image.PreserveAspectCrop
                sourceSize.width: Math.min(app.light ? 280 : 400, Math.max(160, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
                opacity: status === Image.Ready ? (card.installed || !card.dim ? 1 : 0.78) : 0
                Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 200 } }
            }

            // A soft streak of light sweeps across the cover when it is pointed at.
            Rectangle {
                id: shine
                visible: false
                y: -parent.height * 0.3
                width: parent.width * 0.45
                height: parent.height * 1.6
                rotation: 18
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.alpha("white", 0.16) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                NumberAnimation on x {
                    id: sweep
                    running: false
                    from: -shine.width * 1.4; to: card.width + shine.width * 0.4
                    duration: 700; easing.type: Easing.OutCubic
                    onStarted: shine.visible = true
                    onFinished: shine.visible = false
                }
            }
            Connections {
                target: hover
                function onHoveredChanged() { if (hover.hovered && !app.light && img.status === Image.Ready) sweep.restart() }
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

            // Install / update progress: the cover stays visible; a strip along the bottom
            // says what is happening, with the bar running along the very edge.
            Item {
                visible: card.job !== ""
                anchors.fill: parent
                Rectangle { anchors.fill: parent; color: Qt.alpha("black", 0.22) }
                Rectangle {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: 64
                    gradient: Gradient {
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 0.45; color: Qt.alpha("black", 0.7) }
                        GradientStop { position: 1; color: Qt.alpha("black", 0.88) }
                    }
                }
                Row {
                    anchors { left: parent.left; bottom: parent.bottom; leftMargin: 12; bottomMargin: 14 }
                    spacing: 7
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: card.job === "uninstall" ? "trash-2" : card.job === "update" ? "arrow-up" : card.job === "dlc" ? "puzzle" : "download"
                        size: 14; color: "white"
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        color: "white"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        text: card.job === "uninstall" ? "Removing…"
                              : card.progress < 0 ? "Starting…"
                              : (card.job === "update" ? "Updating " : card.job === "dlc" ? "DLC " : "Installing ") + Math.floor(card.progress) + "%"
                    }
                }
                Rectangle {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: 4
                    color: Qt.alpha("white", 0.18)
                    Rectangle {
                        height: parent.height
                        color: theme.primary
                        width: card.progress < 0 ? parent.width * 0.3 : parent.width * Math.max(0.02, card.progress / 100)
                        Behavior on width { NumberAnimation { duration: 300 } }
                        // No percentage yet: a short bar slides back and forth.
                        SequentialAnimation on x {
                            running: card.job !== "" && card.progress < 0 && !app.light
                            loops: Animation.Infinite
                            NumberAnimation { from: 0; to: card.width * 0.6; duration: 900; easing.type: Easing.InOutQuad }
                            NumberAnimation { from: card.width * 0.6; to: 0; duration: 900; easing.type: Easing.InOutQuad }
                        }
                    }
                }
            }
        }

        Rectangle { id: mask; anchors.fill: parent; radius: frame.radius; layer.enabled: true; visible: false }

        // Store chip: shown while the card is pointed at or selected, so covers stay clean.
        Rectangle {
            visible: card.showBadge && opacity > 0
            opacity: card.lit ? 1 : 0
            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 140 } }
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

        // ProtonDB rating, under the store chip (the bottom is used by the title and progress).
        Rectangle {
            visible: card.showProtonDb && card.protondb !== "" && opacity > 0
            opacity: card.lit ? 1 : 0
            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 140 } }
            x: 10; y: card.showBadge ? 38 : 10
            height: 22; radius: 11
            width: pdbText.implicitWidth + 31
            color: "#cc000000"
            StoreIcon { x: 7; anchors.verticalCenter: parent.verticalCenter; size: 12; store: "protondb"; color: ProtonDB.color(card.protondb) }
            Text { id: pdbText; x: 23; anchors.verticalCenter: parent.verticalCenter; text: ProtonDB.label(card.protondb); color: "white"; font.pixelSize: 11 }
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

    // Off while a pop-up is open (and just after one closes), so a click meant for the
    // pop-up never reaches the card underneath.
    property bool interactive: true
    HoverHandler { id: hover; enabled: card.interactive; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        enabled: card.interactive
        onSingleTapped: if (card.interactive) card.opened()
        onDoubleTapped: if (card.interactive) card.activated()
    }
}
