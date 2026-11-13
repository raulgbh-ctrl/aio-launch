import QtQuick
import QtQuick.Layouts

// Humble Bundle's shop window, on the Humble Bundle page: this month's Humble Choice games and the
// game bundles on sale, with their prices. A click opens the page on humblebundle.com.
Column {
    id: shop
    required property var theme
    property bool shown: false
    readonly property var data_: app.humbleShop
    readonly property bool hasChoice: (data_.games || []).length > 0
    readonly property bool hasBundles: (data_.bundles || []).length > 0
    // How each Choice game is delivered, as Humble names it.
    readonly property var stores: ({ steam: qsTr("Steam key"), blizzard: qsTr("Battle.net key"), epic: qsTr("Epic Games key"),
                                      gog: qsTr("GOG key"), origin: qsTr("EA app key"), uplay: qsTr("Ubisoft Connect key"),
                                      external_key: qsTr("Code for another service"), download: qsTr("DRM-free download") })

    visible: shown && (hasChoice || hasBundles)
    height: visible ? implicitHeight : 0
    topPadding: 4
    bottomPadding: 20
    spacing: 22

    onShownChanged: if (shown) app.loadHumbleShop()
    Component.onCompleted: if (shown) app.loadHumbleShop()

    component Head: RowLayout {
        id: head
        property string icon
        property string title
        property string note: ""
        property string action
        signal picked()
        x: 8
        width: shop.width - 16
        spacing: 8
        Icon { name: head.icon; size: 15; color: shop.theme.primary }
        Text { text: head.title; color: shop.theme.onSurface; font.pixelSize: 15; font.weight: Font.DemiBold }
        Text { visible: head.note !== ""; text: "·  " + head.note; color: shop.theme.outline; font.pixelSize: 13 }
        Item { Layout.fillWidth: true }
        Text {
            text: head.action + "  ↗"
            color: headHover.hovered ? shop.theme.primary : shop.theme.onSurfaceVariant
            font.pixelSize: 13; font.weight: Font.DemiBold
            HoverHandler { id: headHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: head.picked() }
        }
    }

    // A tile: wide picture on top, then up to three lines of text.
    component Tile: Rectangle {
        id: tile
        property string image
        property string title
        property string line1
        property color line1Color: shop.theme.primary
        property string line2: ""
        property string badge: ""
        property string url
        width: 268; height: 236
        radius: 12
        color: shop.theme.surfaceContainerHigh
        RoundedArt {
            id: pic
            width: parent.width; height: 151
            radius: tile.radius
            ArtImage { anchors.fill: parent; sources: tile.image ? [tile.image] : []; sourceSize.width: 536 }
        }
        Rectangle {
            visible: tile.badge !== ""
            anchors { top: parent.top; right: parent.right; margins: 8 }
            radius: 8; height: 24; width: badgeText.implicitWidth + 16
            color: shop.theme.primary
            Text { id: badgeText; anchors.centerIn: parent; text: tile.badge; color: shop.theme.onPrimary; font.pixelSize: 12; font.weight: Font.DemiBold }
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: pic.bottom; margins: 12; topMargin: 9 }
            spacing: 4
            Text {
                width: parent.width
                text: tile.title
                font.family: app.titleFamily
                color: shop.theme.onSurface
                font.pixelSize: 14; font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text { width: parent.width; text: tile.line1; color: tile.line1Color; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideRight }
            Text { width: parent.width; visible: tile.line2 !== ""; text: tile.line2; color: shop.theme.outline; font.pixelSize: 12; elide: Text.ElideRight }
        }
        Rectangle {
            anchors.fill: parent; radius: tile.radius; color: "transparent"; z: 1
            border.width: tileHover.hovered ? 2 : 0
            border.color: shop.theme.primary
        }
        HoverHandler { id: tileHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: app.openUrl(tile.url) }
    }

    // --- Humble Choice ---------------------------------------------------------
    Column {
        visible: shop.hasChoice
        width: shop.width
        spacing: 10
        Head {
            icon: "gift"
            title: qsTr("Humble Choice") + (shop.data_.month ? "  ·  " + shop.data_.month : "")
            note: shop.data_.price ? qsTr("%1 games for %2 a month").arg((shop.data_.games || []).length).arg(shop.data_.price) : ""
            action: qsTr("See Choice")
            onPicked: app.openUrl(shop.data_.url)
        }
        ListView {
            x: 8
            width: shop.width - 16
            height: 236
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: shop.data_.games || []
            delegate: Tile {
                required property var modelData
                image: modelData.image
                title: modelData.title
                line1: modelData.owned ? qsTr("In your library") : modelData.worth ? qsTr("Worth %1 on its own").arg(modelData.worth) : ""
                line1Color: modelData.owned ? shop.theme.primary : shop.theme.onSurfaceVariant
                line2: ((modelData.platforms || []).indexOf("linux") !== -1 ? qsTr("Runs on Linux") + "  \u00B7  " : "")
                       + (shop.stores[modelData.store] || "")
                badge: modelData.owned ? "✓" : ""
                url: shop.data_.url
            }
        }
    }

    // --- Game bundles ----------------------------------------------------------
    Column {
        visible: shop.hasBundles
        width: shop.width
        spacing: 10
        Head {
            icon: "tag"
            title: qsTr("Game bundles")
            note: (shop.data_.bundles || []).length + ""
            action: qsTr("All bundles")
            onPicked: app.openUrl(shop.data_.bundlesUrl)
        }
        ListView {
            x: 8
            width: shop.width - 16
            height: 236
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: shop.data_.bundles || []
            delegate: Tile {
                required property var modelData
                image: modelData.image
                title: modelData.title
                line1: (modelData.price || "")
                       + (modelData.items ? "  ·  " + qsTr("%1 items").arg(modelData.items) : "")
                line2: (modelData.when ? qsTr("Until ") + modelData.when + "  ·  " : "") + (modelData.includes || []).join(", ")
                url: modelData.url
            }
        }
    }
}
