import QtQuick
import QtMultimedia

// The focused game's trailer, muted, behind TV mode's text. Loaded through a Loader only
// where Qt Multimedia exists, so the app still starts without it.
Item {
    id: tr
    property string source: ""
    readonly property bool showing: player.playbackState === MediaPlayer.PlayingState && player.position > 400
    opacity: showing ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 700; easing.type: Easing.InOutQuad } }

    AudioOutput { id: silent; muted: true }
    MediaPlayer {
        id: player
        source: tr.source
        loops: MediaPlayer.Infinite
        videoOutput: video
        audioOutput: silent
        onSourceChanged: if (source.toString() !== "") play()
    }
    VideoOutput {
        id: video
        anchors.fill: parent
        fillMode: VideoOutput.PreserveAspectCrop
    }
}
