import QtQuick

// An Image that works through a list of sources, best first, until one loads.
Image {
    id: art
    property var sources: []
    property int at: 0
    property string sig: ""
    // A model refresh hands over a new but equal list: only start over when it really changed.
    onSourcesChanged: {
        const s = JSON.stringify(sources || [])
        if (s !== sig) { sig = s; at = 0 }
    }
    source: sources && sources.length > at ? sources[at] : ""
    asynchronous: true
    fillMode: Image.PreserveAspectCrop
    onStatusChanged: if (status === Image.Error && sources && at < sources.length - 1) at++
}
