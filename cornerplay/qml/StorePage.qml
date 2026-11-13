import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The Store: everything to grab or buy, from every store, on one page. Free to keep (Epic's
// free games and giveaways on other stores), sales on your wishlist, Humble Choice and Humble's
// game bundles, and Steam bundles priced for you. Opened from the sidebar; the sidebar stays.
Popup {
    id: store
    required property var theme
    modal: false
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape
    background: Rectangle { color: store.theme.background }
    readonly property var free: (app.epicFreeAll || []).map(g => ({ title: g.title, url: g.url, art: [g.tall, g.wide].filter(u => !!u),
                                                                   shop: "Epic Games", owned: g.owned, now: g.now, when: g.when }))
                                .concat((app.otherFree || []).map(g => ({ title: g.title, url: g.url, art: [g.tall, g.wide].filter(u => !!u),
                                                                          shop: g.shop || "", owned: g.owned, now: true, when: g.when })))
    readonly property var sales: app.wishlistSalesAll || []
    onOpened: { flick.contentY = 0; app.loadHumbleShop(); app.loadSteamBundles() }

    component Head: RowLayout {
        id: head
        property string icon
        property string title
        property string note: ""
        width: parent ? parent.width : 0
        spacing: 8
        Icon { name: head.icon; size: 16; color: store.theme.primary }
        Text { text: head.title; color: store.theme.onSurface; font.pixelSize: 16; font.weight: Font.DemiBold }
        Text { visible: head.note !== ""; text: "·  " + head.note; color: store.theme.outline; font.pixelSize: 13
               Layout.fillWidth: true; elide: Text.ElideRight }
        Item { Layout.fillWidth: true; visible: head.note === "" }
    }

    // A game tile: tall cover on the left, then title, a price or date line, and the store.
    component Card: Rectangle {
        id: card
        property var art: []
        property string title
        property string line1
        property color line1Color: store.theme.primary
        property string line2: ""
        property string badge: ""
        property string url
        width: 300; height: 132; radius: 12
        color: store.theme.surfaceContainerHigh
        RoundedArt {
            anchors.fill: parent; radius: card.radius
            ArtImage { width: 94; height: parent.height; sources: card.art; sourceSize.width: 188 }
        }
        Rectangle {
            visible: card.badge !== ""
            x: 6; y: 6; radius: 8; height: 22; width: badgeT.implicitWidth + 14; color: store.theme.primary
            Text { id: badgeT; anchors.centerIn: parent; text: card.badge; color: store.theme.onPrimary; font.pixelSize: 11; font.weight: Font.Bold }
        }
        Column {
            anchors { left: parent.left; leftMargin: 94 + 12; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
            spacing: 5
            Text { width: parent.width; text: card.title; font.family: app.titleFamily; color: store.theme.onSurface
                   font.pixelSize: 14; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
            Text { width: parent.width; text: card.line1; color: card.line1Color; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideRight }
            Text { width: parent.width; visible: card.line2 !== ""; text: card.line2; color: store.theme.outline; font.pixelSize: 12; elide: Text.ElideRight }
        }
        Rectangle { anchors.fill: parent; radius: card.radius; color: "transparent"; z: 1
                    border.width: cardHover.hovered ? 2 : 0; border.color: store.theme.primary }
        HoverHandler { id: cardHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: app.openUrl(card.url) }
    }

    contentItem: Flickable {
        id: flick
        clip: true
        contentWidth: width
        contentHeight: col.implicitHeight + 40
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: KScrollBar { }
        Column {
            id: col
            x: Math.max(24, Math.round((flick.width - 1300) / 2))
            width: flick.width - 2 * x
            y: 24
            spacing: 26

            RowLayout {
                width: parent.width
                spacing: 12
                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    Text { text: qsTr("Store"); color: store.theme.onSurface; font.family: app.titleFamily; font.pixelSize: 28; font.weight: Font.Bold }
                    Text {
                        width: parent.width; wrapMode: Text.WordWrap
                        text: qsTr("Free games, sales on your wishlist and bundles from every store, in one place. Games you own are marked.")
                        color: store.theme.onSurfaceVariant; font.pixelSize: 13
                    }
                }
                KButton { theme: store.theme; iconName: "x"; ToolTip.visible: hovered; ToolTip.text: qsTr("Back to the library (Esc)"); onClicked: store.close() }
            }

            // Free to keep
            Column {
                visible: store.free.length > 0
                width: parent.width
                spacing: 10
                Head {
                    readonly property int n: store.free.filter(g => g.now && !g.owned).length
                    icon: "gift"; title: qsTr("Free to keep"); note: n ? qsTr("%1 now").arg(n) : ""
                }
                Flow {
                    width: parent.width
                    spacing: 12
                    Repeater {
                        model: store.free
                        Card {
                            required property var modelData
                            art: modelData.art; title: modelData.title; url: modelData.url
                            line1: modelData.owned ? qsTr("In your library") : modelData.now ? (modelData.when ? qsTr("Free until ") + modelData.when : qsTr("Free now"))
                                                                                             : qsTr("Free from ") + modelData.when
                            line1Color: modelData.now && !modelData.owned ? store.theme.primary : store.theme.outline
                            line2: modelData.shop
                            badge: modelData.now && !modelData.owned ? qsTr("FREE") : ""
                        }
                    }
                }
            }

            // Sales on your wishlist (the store's own sale, or IsThereAnyDeal's cheaper one)
            Column {
                visible: store.sales.length > 0
                width: parent.width
                spacing: 10
                Head { icon: "tag"; title: qsTr("On sale from your wishlist"); note: store.sales.length + "" }
                Flow {
                    width: parent.width
                    spacing: 12
                    Repeater {
                        model: store.sales
                        Card {
                            required property var modelData
                            readonly property var best: modelData.best && modelData.best.cut > (modelData.discount || 0) ? modelData.best : null
                            art: [modelData.tall, modelData.wide].filter(u => !!u); title: modelData.title
                            url: best ? best.url : modelData.url
                            badge: "-" + (best ? best.cut : modelData.discount) + "%"
                            readonly property string was: (best ? best.was : modelData.was) || ""
                            line1: best ? best.price : modelData.price
                            line2: (was ? qsTr("was %1").arg(was) + "  ·  " : "")
                                   + (best ? best.shop + (best.low ? "  ·  " + qsTr("lowest ever") : "") : (modelData.store === "gog" ? "GOG" : "Steam"))
                        }
                    }
                }
            }

            // Humble Choice and Humble's game bundles (tiers priced against buying separately)
            HumbleShop { width: parent.width; theme: store.theme; shown: store.opened }

            // Steam bundles priced for you
            SteamBundles { width: parent.width; theme: store.theme; shown: store.opened }

            Text {
                visible: store.free.length === 0 && store.sales.length === 0
                width: parent.width; wrapMode: Text.WordWrap
                text: qsTr("Wishlist sales show here once Settings › Library › wishlists on sale is on.")
                color: store.theme.outline; font.pixelSize: 12
            }
        }
    }
}
