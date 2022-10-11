
# Placed into Public Domain in June 2006 by Sean D. Spencer

# Sean D. Spencer
# sean_don4@lycos.com
# 2/19/2006
# Last Revision: 4/19/2007

# MIDI Parsing Library for Python.

from io import BufferedReader


TRUE = -1
FALSE = 0
MIDI_HEADER = 0x4D546864
MIDI_TRACK = 0x4D54726B

class format:
    SingleTrack = 0
    MultipleTracksSync = 1
    MultipleTracksAsync = 2


class voice:
    NoteOff = 0x80
    NoteOn = 0x90
    PolyphonicKeyPressure = 0xA0  # note aftertouch
    ControllerChange = 0xB0
    ProgramChange = 0xC0
    ChannelPressure = 0xD0
    PitchBend = 0xE0


class meta:
    FileMetaEvent = 0xFF
    SMPTEOffsetMetaEvent = 0x54
    SystemExclusive = 0xF0
    SystemExclusivePacket = 0xF7
    SequenceNumber = 0x00
    TextMetaEvent = 0x01
    CopyrightMetaEvent = 0x02
    TrackName = 0x03
    InstrumentName = 0x04
    Lyric = 0x05
    Marker = 0x06
    CuePoint = 0x07
    ChannelPrefix = 0x20
    MidiPort = 0x21
    EndTrack = 0x2F
    SetTempo = 0x51
    TimeSignature = 0x58
    KeySignature = 0x59
    SequencerSpecificMetaEvent = 0x7F


class EventNote:
    def __init__(self):
        self.note_no = None
        self.velocity = None


class EventValue:
    def __init__(self):
        self.type = None
        self.value = None


class EventAmount:
    def __init__(self):
        self.amount = None


class MetaEventKeySignature:
    def __init__(self):
        self.fifths = None
        self.mode = None


class MetaEventTimeSignature:
    def __init__(self):
        self.numerator = None
        self.log_denominator = None
        self.midi_clocks = None
        self.thirty_seconds = None


class MetaEventText:
    def __init__(self):
        self.length = None
        self.text = None


class MetaEventSMPTEOffset:
    def __init__(self):
        self.hour = None
        self.minute = None
        self.second = None
        self.frame = None
        self.sub_frame = None


class MetaValues:
    def __init__(self):
        self.length = None
        self.values = None

def checkByte(ordval):
    if not type(ordval) is int or ordval > 255 or ordval < 0:
        raise IndexError("Byte value was out of bounds, or not of type int: " + repr(type(ordval)))
    return ordval

def getNumber(theString, length):
    # MIDI uses big-endian for everything
    sum = 0
    #print "Length: " + str(length) + "  strlen: " + str(len(theString))
    for i in range(length):
        #sum = (sum *256) + int(str[i])
        sum = (sum << 8) + theString[i]
    return sum, theString[length:]


def getVariableLengthNumber(str):
    sum = 0
    i = 0
    while 1:
        x = checkByte(str[i])
        i = i + 1
        # sum = (sum * 127) + (x (mask) 127) # mask off the 7th bit
        sum = (sum << 7) + (x & 0x7F)
        # Is 7th bit clear?
        if not (x & 0x80):
            return sum, str[i:]


def getValues(str, n=16):
    temp = []
    for x in str[:n]:
        temp.append(repr(checkByte(x)))
    return temp

class Chunk:
    chunkNumber = 1
    track_num = 1
    def __init__(self, file: BufferedReader):
        self.file = file
        self.valid = False
        self.chunkNumber = Chunk.chunkNumber
        Chunk.chunkNumber += 1
        self.raw_type = self.file.read(4)
        if len(self.raw_type) == 0:
            self.file.close()
            return
        self.type = int.from_bytes(self.raw_type,byteorder='big')
        self.length = int.from_bytes(self.file.read(4), byteorder='big')
        self.data = self.file.read(self.length)
        self.values = {}
        self.valid = True
        if self.type == MIDI_HEADER: #MThd -Header-
            self.values["format"] = ["int",0,2,"big"]
            if self["format"] == 0:
                self.values["format_description"] = ["stored", "A single multi-channel track"]
            elif self["format"] == 1:
                self.values["format_description"] = ["stored", "One or more simultaneous tracks (or MIDI outputs) of a sequence"]
            elif self["format"] == 2:
                self.values["format_description"] = ["stored", "One or more sequentially independent single-track patterns"]
            else:
                self.values["format_description"] = ["stored", f"Format number '{self['format']}' is unknown"]
            self.values["tracks"] = ["int",2,2,"big"]
            self.values["division"] = ["int",4,2,"big"]
            self.values["division_15th_bit"] = ["bit",4,7]
            if self["division_15th_bit"] == 0:
                self.values["division_description"] = ["stored", "Ticks are per quarter-note"]
                self.values["division_ticks_per_qnote"] = ["bitmask",4,2,"big",~0x8000]
            else:
                self.values["division_description"] = ["stored", "Negative SMPTE format and ticks per frame"]
                self.values["division_ticks_per_frame"] = ["int",5,1,"big"]
                self.values["division_SMPTE_format"] = ["bitmask",4,1,"big",0x7F]
                self.values["division_SMPTE_format_description"] = ["stored", "24 fps, 25 fps, 29.97fps (-29) or 30fps"]
        elif self.type == MIDI_TRACK: #MTrk -Track-
            track = Track(Chunk.track_num)
            self.values["track"] = ["stored", track]
            Chunk.track_num += 1
            track.read(self)
        else: #Unknown
            raise TypeError(f"Unknown MIDI chunk: '{self.raw_type}'")
    def __getitem__(self, attr):
        if attr in self.values:
            if self.values[attr][0] == "int":
                return int.from_bytes(self.data[self.values[attr][1]:self.values[attr][1]+self.values[attr][2]], byteorder=self.values[attr][3])
            elif self.values[attr][0] == "stored":
                return self.values[attr][1]
            elif self.values[attr][0] == "bit":
                 return (self.data[self.values[attr][1]] & (1 << self.values[attr][2])) >> self.values[attr][2]
            elif self.values[attr][0] == "bitmask":
                return int.from_bytes(self.data[self.values[attr][1]:self.values[attr][1]+self.values[attr][2]], byteorder=self.values[attr][3]) & self.values[attr][4]
        else:
            raise TypeError(f"Chunk doesn't contain value for '{attr}'")
    def __str__(self) -> str:
        retString = f"\nChunk {self.chunkNumber} - Type: '{self.raw_type.decode('latin_1')}':\n"
        retString += f"\tType:     " + '{0:#0{1}x}'.format(self.type,10) + "\n"
        retString += f"\tLength:        " + repr(self.length).rjust(5," ") + " bytes\n"
        retString += f"\tNo. attributes:" + repr(len(self.values)).rjust(5, " ") + "\n"
        retString += f"Chunk[<attr>] values/attributes:\n\n"
        maxAttrLen = 0
        maxValLen = 0
        for attr in self.values:
            if attr[-12:] != "_description":
                maxAttrLen = max(len(attr),maxAttrLen)
                maxValLen = max(len(repr(self[attr])),maxValLen)
        for attr in self.values:
            if attr[-12:] != "_description":
                retString += f"\t" + repr(attr).ljust(maxAttrLen," ") + "\t" + repr(self[attr]).rjust(maxValLen," ")
                if (attr + "_description") in self.values:
                    retString += "\t(" + self[attr + "_description"] + ")\n"
                else:
                    retString += "\n"
        return retString

class File:
    def __init__(self, file):
        self.file = file
        self.format = None
        self.num_tracks = None
        self.division = None
        self.tracks = []
        self.file = open(self.file, 'rb')
        self.read()

    def read(self):
        #print("STR:","Thus;",str[:4].decode("utf-8"))
        chunk = Chunk(self.file)
        self.format = chunk["format"]
        self.num_tracks = chunk["tracks"]
        self.division = chunk["division"]
        while chunk.valid:
            if chunk.type == MIDI_TRACK:
                self.tracks.append(chunk["track"])
            chunk = Chunk(self.file)
        

class Track:
    def __init__(self, index):
        self.number = index
        self.length = None
        self.events = []

    def read(self, chunk: Chunk):
        self.length = chunk.length
        track_str = bytearray(chunk.data)
        prev_absolute = 0
        prev_status = 0

        i = 0
        while track_str:
            event = Event(self.number, i+1)
            track_str = event.read(prev_absolute, prev_status, track_str)
            #print("Event Type: ", event.type)

            prev_absolute += event.delta
            prev_status = event.status
            self.events.append(event)
            i += 1

        return chunk


class Event:
    def __init__(self, track, index):
        self.number = index
        self.type = None
        self.delta = None
        self.absolute = None
        self.status = None
        self.channel = None

    def read(self, prev_time, prev_status, str):
        self.delta, str = getVariableLengthNumber(str)
        self.absolute = prev_time + self.delta

        # use running status?
        if not (checkByte(str[0]) & 0x80):
            # squeeze a duplication of the running status into the data string
            str.insert(1,prev_status)

        self.status = str[0]
        self.channel = checkByte(self.status) & 0xF

        # increment one byte, past the status
        str = str[1:]

        has_channel = has_meta = TRUE

        # handle voice events
        channel_msg = checkByte(self.status) & 0xF0
        if channel_msg == voice.NoteOn or \
                channel_msg == voice.NoteOff or \
                channel_msg == voice.PolyphonicKeyPressure:
            self.detail = EventNote()
            self.detail.note_no = checkByte(str[0])
            self.detail.velocity = checkByte(str[1])
            str = str[2:]

        elif channel_msg == voice.ControllerChange:
            self.detail = EventValue()
            self.detail.type = checkByte(str[0])
            self.detail.value = checkByte(str[1])
            str = str[2:]

        elif channel_msg == voice.ProgramChange or \
                channel_msg == voice.ChannelPressure:

            self.detail = EventAmount()
            self.detail.amount = checkByte(str[0])
            str = str[1:]

        elif channel_msg == voice.PitchBend:
            # Pitch bend uses high accuracy 14 bit unsigned integer.
            self.detail = EventAmount()
            self.detail.amount = (checkByte(str[0]) << 7) | checkByte(str[1])
            str = str[2:]

        else:
            has_channel = FALSE

        # handle meta events
        meta_msg = checkByte(self.status)
        if meta_msg == meta.FileMetaEvent:

            meta_msg = type = checkByte(str[0])
            length, str = getVariableLengthNumber(str[1:])

            if type == meta.SetTempo or \
                    type == meta.ChannelPrefix:

                self.detail = EventAmount()
                self.detail.tempo, str = getNumber(str, length)

            elif type == meta.KeySignature:
                self.detail = MetaEventKeySignature()
                self.detail.fifths = checkByte(str[0])

                if checkByte(str[1]):
                    self.detail.mode = "minor"
                else:
                    self.detail.mode = "major"

                str = str[length:]

            elif type == meta.TimeSignature:
                self.detail = MetaEventTimeSignature()
                self.detail.numerator = checkByte(str[0])
                self.detail.log_denominator = checkByte(str[1])
                self.detail.midi_clocks = checkByte(str[2])
                self.detail.thirty_seconds = checkByte(str[3])
                str = str[length:]

            elif type == meta.TrackName or \
                    type == meta.TextMetaEvent or \
                    type == meta.Lyric or \
                    type == meta.CuePoint or \
                    type == meta.CopyrightMetaEvent:

                self.detail = MetaEventText()
                self.detail.length = length
                self.detail.text = str[:length]
                str = str[length:]

            elif type == meta.SMPTEOffsetMetaEvent:
                self.detail = MetaEventSMPTEOffset()
                self.detail.hour = checkByte(str[0])
                self.detail.minute = checkByte(str[1])
                self.detail.second = checkByte(str[2])
                self.detail.frame = checkByte(str[3])
                self.detail.sub_frame = checkByte(str[4])
                str = str[length:]

            elif type == meta.EndTrack:
                str = str[length:]  # pass on to next track

            else:
                # skip over unknown meta event
                str = str[length:]

        elif meta_msg == meta.SystemExclusive or \
                meta_msg == meta.SystemExclusivePacket:
            self.detail = MetaValues()
            self.detail.length, str = getVariableLengthNumber(str)
            self.detail.values = getValues(str, self.detail.length)
            str = str[self.detail.length:]

        else:
            has_meta = FALSE

        if has_channel:
            self.type = channel_msg
        elif has_meta:
            self.type = meta_msg
        else:
            raise Exception("Unknown event: %d" % checkByte(self.status))
            # self.type = None
        return str