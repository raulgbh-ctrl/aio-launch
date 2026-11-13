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
    required property bool favourite
    required property real achieved   // 0..1 of the game's achievements earned; -1 when unknown
    required property bool isNew      // bought or claimed this week and not played yet
    required property var heroes
    required property var logos
    // "cover" (the box art), "logo" (wide art with the game's logo: the logo wall) or "box"
    // (a game case with a spine, standing on a shelf). View menu, desktop library only.
    property string style: "cover"
    readonly property real spine: style === "box" ? Math.round(width * 0.075) : 0
    property bool showProtonDb: true
    property int cornerRadius: 14
    property bool showBadge: true
    property bool showTitle: false
    property int gap: 8   // around the cover (Settings > Appearance > Density)
    property bool dim: true
    property string trailer: ""   // a trailer to play inside the cover (the main window sets it while pointed at)
    signal opened()
    signal activated()
    signal menuRequested(point at)
    signal pickRequested(bool range)  // Ctrl+click (one) or Shift+click (a range): several games at once
    property bool picked: false       // one of the games picked for an action
    property bool picking: false      // some game is picked: a plain click picks too  // right-click, or a long press on a touchscreen (in the card's coordinates)

    readonly property bool hovered: hover.hovered
    readonly property bool lit: hover.hovered || current
    // Tilt: the cover tips toward the pointer, like a game case held in the hand (-1..1 each way).
    readonly property bool tilting: hover.hovered && !app.light && GraphicsInfo.api !== GraphicsInfo.Software
    readonly property real tiltX: tilting ? Math.max(-1, Math.min(1, hover.point.position.x / Math.max(1, width) * 2 - 1)) : 0
    readonly property real tiltY: tilting ? Math.max(-1, Math.min(1, hover.point.position.y / Math.max(1, height) * 2 - 1)) : 0

    // Accent glow around the pointed-at card: a soft, blurred light that sits a little low.
    RectangularShadow {
        anchors.fill: frame
        visible: card.lit && !app.light && GraphicsInfo.api !== GraphicsInfo.Software
        radius: frame.radius
        scale: frame.scale
        blur: 30
        spread: 2
        offset.y: 6
        color: Qt.alpha(card.theme.primary, 0.42)
    }
    // Light mode (or no GPU): a few fading outlines instead, cheap on anything.
    Item {
        anchors.fill: frame
        scale: frame.scale
        visible: card.lit && (app.light || GraphicsInfo.api === GraphicsInfo.Software)
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

    // The cover's shadow (Settings > Appearance: none, soft or deep).
    RectangularShadow {
        anchors.fill: frame
        visible: !app.light && !card.lit && (app.settingsMap.card_shadow || "soft") !== "none"
        readonly property bool deep: app.settingsMap.card_shadow === "deep"
        radius: frame.radius
        scale: frame.scale
        blur: deep ? 26 : 12
        spread: 0
        offset.y: deep ? 12 : 5
        color: Qt.alpha("black", deep ? 0.6 : 0.4)
    }
    // Box view: a wooden shelf under each row; the cells sit edge to edge, so the planks join up.
    Rectangle {
        visible: card.style === "box"
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; bottomMargin: card.gap - 2 }
        height: 16
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#a87a4f" }
            GradientStop { position: 0.18; color: "#8a6038" }
            GradientStop { position: 1.0; color: "#5a3c22" }
        }
        Rectangle {  // its shadow on the wall
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.bottom
            height: 10
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.alpha("black", 0.35) }
                GradientStop { position: 1; color: "transparent" }
            }
        }
    }
    Rectangle {
        id: frame
        anchors.fill: parent
        anchors.margins: card.gap
        anchors.bottomMargin: card.style === "box" ? card.gap + 18 : card.gap
        radius: card.cornerRadius
        color: theme.surfaceContainerHigh
        scale: card.lit && !app.light ? 1.03 : 1.0
        Behavior on scale { enabled: !app.light; NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        transform: [
            Rotation {
                origin.x: frame.width / 2; origin.y: frame.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: card.tiltX * 7
                Behavior on angle { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
            },
            Rotation {
                origin.x: frame.width / 2; origin.y: frame.height / 2
                axis { x: 1; y: 0; z: 0 }
                angle: -card.tiltY * 6
                Behavior on angle { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
            }
        ]

        // Box view: the case's spine, with the title running up it.
        Rectangle {
            visible: card.style === "box"
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
            width: card.spine + 6
            radius: 3
            color: Qt.darker(card.storeColor || theme.primary, 2.6)
            Text {
                anchors.centerIn: parent
                width: parent.height - 16
                rotation: -90
                text: card.title
                color: Qt.alpha("white", 0.85)
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                font.family: app.titleFamily
                font.pixelSize: Math.max(8, Math.round(card.spine * 0.55)); font.weight: Font.DemiBold
            }
        }
        Item {
            id: art
            anchors.fill: parent
            anchors.leftMargin: card.spine
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
                    font.family: app.titleFamily
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
            readonly property bool wideArt: card.style === "cover" && img.status === Image.Ready && img.implicitWidth > img.implicitHeight * 1.1
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
                sources: card.style === "logo" ? (card.heroes || []).concat(card.covers) : card.covers
                fillMode: parent.wideArt ? Image.PreserveAspectFit : Image.PreserveAspectCrop
                sourceSize.width: Math.min(app.light ? 280 : 600, Math.max(160, Math.ceil(width * Screen.devicePixelRatio / 40) * 40))
                opacity: status === Image.Ready ? (card.installed || !card.dim ? 1 : 0.78) : 0
                Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 200 } }
            }

            // Logo wall: the game's logo over its wide art (its title when there is no logo).
            Rectangle {
                visible: card.style === "logo"
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0.35; color: "transparent" }
                    GradientStop { position: 1.0; color: Qt.alpha("black", 0.75) }
                }
            }
            Image {
                id: logoImg
                visible: card.style === "logo"
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: parent.width * 0.07 }
                height: parent.height * 0.38
                source: card.style === "logo" ? ((card.logos || [])[0] || "") : ""
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignLeft
                verticalAlignment: Image.AlignBottom
                asynchronous: true
                sourceSize.height: 160
            }
            Text {
                visible: card.style === "logo" && logoImg.status !== Image.Ready
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: parent.width * 0.07 }
                text: card.title
                color: "white"
                wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                font.family: app.titleFamily
                font.pixelSize: Math.round(parent.height * 0.13); font.weight: Font.Bold
            }
            // Box view: the case's plastic catches the light along its hinge.
            Rectangle {
                visible: card.style === "box"
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                width: parent.width * 0.12
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.alpha("white", 0.22) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            // The trailer, muted, inside the cover (fades in once it plays).
            Loader {
                anchors.fill: parent
                active: card.trailer !== "" && typeof canPlayVideo !== "undefined" && canPlayVideo
                source: "TvTrailer.qml"
                onLoaded: item.source = Qt.binding(() => card.trailer)
            }

            // A soft light that follows the pointer across the cover while it tilts.
            RectangularShadow {
                visible: card.tilting && img.status === Image.Ready
                width: parent.width * 0.9; height: width
                x: (card.tiltX + 1) / 2 * parent.width - width / 2
                y: (card.tiltY + 1) / 2 * parent.height - height / 2
                radius: width / 2
                blur: width * 0.45
                color: Qt.alpha("white", 0.13)
                Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
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
                height: Math.min(110, parent.height * 0.45)
                opacity: (card.lit || card.showTitle) && img.status === Image.Ready ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 0.55; color: Qt.alpha("black", 0.55) }
                    GradientStop { position: 1; color: Qt.alpha("black", 0.9) }
                }
                Text {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12; bottomMargin: 11 }
                    text: card.title
                    color: "white"
                    font.pixelSize: 14
                    font.family: app.titleFamily
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
                        name: card.job === "uninstall" ? "trash-2" : card.job === "update" ? "arrow-up" : card.job === "dlc" ? "puzzle" : card.job === "move" ? "folder-open" : "download"
                        size: 14; color: "white"
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        color: "white"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        text: card.job === "uninstall" ? qsTr("Removing…") : card.job === "queued" ? qsTr("Queued")
                              : card.job === "paused" ? qsTr("Paused") + (card.progress >= 0 ? " · " + Math.floor(card.progress) + "%" : "")
                              : card.progress < 0 ? qsTr("Starting…")
                              : (card.job === "update" ? qsTr("Updating ") : card.job === "dlc" ? qsTr("DLC ") : card.job === "move" ? qsTr("Moving ") : card.job === "verify" ? qsTr("Checking ") : card.job === "fix" ? qsTr("Fixing ") : qsTr("Installing ")) + Math.floor(card.progress) + "%"
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
                            running: card.job !== "" && card.job !== "paused" && card.job !== "queued" && card.progress < 0 && !app.light
                            loops: Animation.Infinite
                            NumberAnimation { from: 0; to: card.width * 0.6; duration: 900; easing.type: Easing.InOutQuad }
                            NumberAnimation { from: card.width * 0.6; to: 0; duration: 900; easing.type: Easing.InOutQuad }
                        }
                    }
                }
            }
        }

        Rectangle { id: mask; anchors.fill: parent; radius: frame.radius; layer.enabled: true; visible: false }

        // Achievements earned: a thin bar along the bottom edge, in gold once all are done.
        Item {
            visible: card.achieved > 0 && card.job === "" && opacity > 0
            opacity: card.lit || card.achieved >= 1 ? 1 : 0.85
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
            height: 4
            Rectangle { anchors.fill: parent; radius: 2; color: Qt.alpha("black", 0.45) }
            Rectangle {
                height: parent.height; radius: 2
                width: Math.max(height, parent.width * Math.min(1, card.achieved))
                color: card.achieved >= 1 ? "#ffd166" : card.theme.primary
            }
        }

        // Store chip: shown while the card is pointed at or selected, so covers stay clean.
        Rectangle {
            visible: card.showBadge && opacity > 0
            opacity: card.lit ? 1 : 0
            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 140 } }
            x: 10; y: 10
            height: 22; radius: 11
            width: chip.implicitWidth + 31
            color: Qt.alpha("black", 0.58)
            border.width: 1; border.color: Qt.alpha("white", 0.14)
            StoreIcon { x: 7; anchors.verticalCenter: parent.verticalCenter; size: 12; store: card.store; color: card.storeColor }
            Text { id: chip; x: 23; anchors.verticalCenter: parent.verticalCenter; text: card.storeName + (card.copies > 1 ? "  +" + (card.copies - 1) : ""); color: "white"; font.pixelSize: 11 }
        }

        // New: bought or claimed this week, not played yet. Gives way to the store chip when pointed at.
        Rectangle {
            visible: card.isNew && opacity > 0
            opacity: card.lit ? 0 : 1
            Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 140 } }
            x: 10; y: 10
            height: 20; radius: 10
            width: newText.implicitWidth + 18
            color: card.theme.primary
            Text { id: newText; anchors.centerIn: parent; text: qsTr("NEW"); color: card.theme.onPrimary
                   font.pixelSize: 10; font.weight: Font.Black; font.letterSpacing: 1.0 }
        }

        // Not-installed marker.
        Rectangle {
            visible: !card.installed && card.job === ""
            anchors { right: parent.right; top: parent.top; margins: 10 }
            width: 22; height: 22; radius: 11
            color: Qt.alpha("black", 0.58)
            border.width: 1; border.color: Qt.alpha("white", 0.14)
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
            color: Qt.alpha("black", 0.58)
            border.width: 1; border.color: Qt.alpha("white", 0.14)
            StoreIcon { x: 7; anchors.verticalCenter: parent.verticalCenter; size: 12; store: "protondb"; color: ProtonDB.color(card.protondb) }
            Text { id: pdbText; x: 23; anchors.verticalCenter: parent.verticalCenter; text: ProtonDB.label(card.protondb); color: "white"; font.pixelSize: 11 }
        }

        // Favourite marker, top right (moves left of the update marker when both show).
        Rectangle {
            visible: card.favourite
            anchors { right: parent.right; top: parent.top; margins: 10; rightMargin: card.installed && card.update && card.job === "" ? 38 : 10 }
            width: 22; height: 22; radius: 11
            color: Qt.alpha("black", 0.58)
            border.width: 1; border.color: Qt.alpha("white", 0.14)
            Icon { anchors.centerIn: parent; name: "star-filled"; size: 12; color: "#ffd166" }
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
            border.color: card.lit ? theme.primary
                          : theme.dark === false ? Qt.alpha("black", 0.10) : Qt.alpha("white", 0.09)
        }
    }

    // Off while a pop-up is open (and just after one closes), so a click meant for the
    // pop-up never reaches the card underneath.
    property bool interactive: true
    HoverHandler { id: hover; enabled: card.interactive; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        enabled: card.interactive
        acceptedModifiers: Qt.NoModifier
        onSingleTapped: if (card.interactive) { if (card.picking) card.pickRequested(false); else card.opened() }
        onDoubleTapped: if (card.interactive && !card.picking) card.activated()
        onLongPressed: if (card.interactive) card.menuRequested(point.position)
    }
    TapHandler { enabled: card.interactive; acceptedModifiers: Qt.ControlModifier; onTapped: card.pickRequested(false) }
    TapHandler { enabled: card.interactive; acceptedModifiers: Qt.ShiftModifier; onTapped: card.pickRequested(true) }
    // Picked: a ring in the accent colour and a tick in the corner.
    Rectangle {
        visible: card.picked
        anchors.fill: parent; anchors.margins: card.gap / 2 - 2
        radius: card.cornerRadius + 2
        color: Qt.alpha(card.theme.primary, 0.12)
        border.width: 3; border.color: card.theme.primary
        z: 50
        Rectangle {
            x: 10; y: 10; width: 26; height: 26; radius: 13
            color: card.theme.primary
            Icon { anchors.centerIn: parent; name: "check"; size: 16; color: card.theme.onPrimary }
        }
    }
    TapHandler {
        enabled: card.interactive
        acceptedButtons: Qt.RightButton
        onTapped: (eventPoint, button) => card.menuRequested(eventPoint.position)
    }
}
