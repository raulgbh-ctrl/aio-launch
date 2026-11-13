import QtQuick
import QtQuick.Layouts

// On the Steam page: bundles with games from your wishlist, and bundles that only add DLC or
// soundtracks to games you own, each priced for you (Steam leaves out what you already own).
Column {
    id: sb
    required property var theme
    property bool shown: false
    property var d: ({})
    readonly property var wish: d.wishlist || []
    readonly property var extras: d.extras || []
    visible: shown && (wish.length > 0 || extras.length > 0)
    height: visible ? implicitHeight : 0
    topPadding: 4
    bottomPadding: 20
    spacing: 22
    onShownChanged: if (shown) app.loadSteamBundles()
    Component.onCompleted: if (shown) app.loadSteamBundles()
    Connections { target: app; function onSteamBundlesReady(data) { sb.d = data } }
    Connections { target: app; function onWishlistChanged() { if (sb.shown) app.loadSteamBundles() } }

    component Row_: Column {
        id: row
        property string icon
        property string title
        property string note
        property var model
        property bool showWish: false
        visible: model.length > 0
        width: sb.width
        spacing: 10
        RowLayout {
            x: 8; width: sb.width - 16; spacing: 8
            Icon { name: row.icon; size: 15; color: sb.theme.primary }
            Text { text: row.title + "  ·  " + row.model.length; color: sb.theme.onSurface; font.pixelSize: 15; font.weight: Font.DemiBold }
            Text { text: row.note; color: sb.theme.outline; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
        }
        ListView {
            x: 8; width: sb.width - 16; height: 214
            orientation: ListView.Horizontal; spacing: 12; clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: row.model
            delegate: Rectangle {
                id: tile
                required property var modelData
                width: 268; height: 214; radius: 12
                color: sb.theme.surfaceContainerHigh
                RoundedArt {
                    id: pic
                    width: parent.width; height: 125; radius: tile.radius
                    ArtImage { anchors.fill: parent; sources: tile.modelData.image ? [tile.modelData.image] : []; sourceSize.width: 536 }
                }
                Rectangle {
                    visible: tile.modelData.saving > 0
                    anchors { top: parent.top; right: parent.right; margins: 8 }
                    radius: 8; height: 24; width: cut.implicitWidth + 16; color: sb.theme.primary
                    Text { id: cut; anchors.centerIn: parent; text: "-" + tile.modelData.saving + "%"; color: sb.theme.onPrimary; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
                Column {
                    anchors { left: parent.left; right: parent.right; top: pic.bottom; margins: 12; topMargin: 8 }
                    spacing: 3
                    Text { width: parent.width; text: tile.modelData.name; font.family: app.titleFamily; color: sb.theme.onSurface
                           font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight }
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        font.pixelSize: 13; font.weight: Font.DemiBold; color: sb.theme.primary
                        text: qsTr("%1 for you").arg(tile.modelData.forYou)
                              + (tile.modelData.ownedCount ? "  ·  " + qsTr("you own %1 of %2").arg(tile.modelData.ownedCount).arg(tile.modelData.count) : "")
                    }
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        font.pixelSize: 12; color: sb.theme.outline
                        text: row.showWish ? qsTr("Wishlist: ") + tile.modelData.wish.join(", ") : qsTr("Adds ") + tile.modelData.adds.join(", ")
                    }
                }
                Rectangle { anchors.fill: parent; radius: tile.radius; color: "transparent"; z: 1
                            border.width: tileHover.hovered ? 2 : 0; border.color: sb.theme.primary }
                HoverHandler { id: tileHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: app.openUrl(tile.modelData.url) }
            }
        }
    }

    Row_ {
        icon: "star"; title: qsTr("Bundles with your wishlist games"); showWish: true; model: sb.wish
        note: qsTr("Cheapest way to each first; Steam takes what you own off the price")
    }
    Row_ {
        icon: "puzzle"; title: qsTr("Complete the set"); model: sb.extras
        note: qsTr("DLC and soundtracks for games you own; any DLC you already have comes off too")
    }
}
