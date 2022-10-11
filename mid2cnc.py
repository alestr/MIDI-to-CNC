#!/usr/bin/env python
# -*- coding: utf-8 -*-
##################################
#
# mid2cnc.py, a MIDI to CNC g-code converter
# by T. R. Gipson <drmn4ea at google mail>
# http://tim.cexx.org/?p=633
# Released under the GNU General Public License
#
##################################
#
# Includes midiparser.py module by Sean D. Spencer
# http://seandon4.tripod.com/
# This module is public domain.
#
##################################
#
# Hacked by Miles Lightwood of TeamTeamUSA to support
# the MakerBot Cupcake CNC - < m at teamteamusa dot com >
#
# Modified to handle multiple axes with the MakerBot 
# by H. Grote <hg at pscht dot com>
#
# Further hacked fully into 3 dimensions and generalised
# for multiple CNC machines by Michael Thomson
# <mike at m-thomson dot net>
# 
##################################
#
# More info on:
# http://groups.google.com/group/makerbotmusic
# 
##################################

# Requires Python 2.7
import argparse

import sys
import os.path
import math

# Import the MIDI parser code from the subdirectory './lib'
import lib.midiparser as midiparser
import mido

active_axes = 3

# Specifications for some machines (Need verification!)
#
machines_dict = dict( {
        'cupcake':[
            'metric',                # Units scheme
            11.767, 11.767, 320.000, # Pulses per unit for X, Y, Z axes
            -20.000, -20.000, 0.000, # Safe envelope minimum for X, Y, Z
            20.000, 20.000, 10.000,  # Safe envelope maximum for X, Y, Z
            'XYZ'                    # Default axes and the order for playing
        ],      

        'thingomatic':[
            'metric',
            47.069852, 47.069852, 200.0,
            -20.000, -20.000, 0.000,
            20.000, 20.000, 10.000,
            'XYZ'
        ],

        'shapercube':[
            'metric',
            10.0, 10.0, 320.0,
            0.000, 0.000, 0.000,
            10.000, 10.000, 10.000,
            'XYZ'
        ],

        'ultimaker':[
            'metric',
            47.069852, 47.069852, 160.0,
            0.000, 0.000, 0.000,
            10.000, 10.000, 10.000,
            'XYZ'
        ],

        'multicam_custom':[
            'metric',
            228.0, 228.0, 393.700775,
            0.000, 0.000, 0.000,
            120.000, 120.000, 20.000,
            'ZYX'
        ],

        'custom':[
            'metric',
            10.0, 10.0, 10.0,
            0.000, 0.000, 0.000,
            10.000, 10.000, 10.000,
            'X'
        ]
    })

# Specifications for the systems of units we know about
#
units_dict = dict( {
        # 'scheme':'units', 'abbreviation', scale_to_mm]
        'metric':[
            'millimetre', 'mm', 1.0
        ],
        'imperial':[
            'inch', 'in', 25.4
        ]
    })
# Specifications for the systems of units we know about
#
rate_dict = dict( {
        # 'scheme':'units', 'abbreviation', feed_rate_factor]
        'minutes':[
            'minute', 'm', 60.0
        ],
        'seconds':[
            'second', 's', 1.0
        ]
    })

# A way to specify any mix of axes in the order you want to voice them
#
axes_dict = dict( {
          'X':[0],       'Y':[1],       'Z':[2],
         'XY':[0,1],    'YX':[1,0],    'XZ':[0,2],
         'ZX':[2,0],    'YZ':[1,2],    'ZY':[2,1],
        'XYZ':[0,1,2], 'XZY':[0,2,1],
        'YXZ':[1,0,2], 'YZX':[1,2,0],
        'ZXY':[2,0,1], 'ZYX':[2,1,0]
    })

def reached_limit(current, distance, direction, min, max):
    # Returns true if the proposed movement will exceed the
    # safe working limits of the machine but the movement is
    # allowable in the reverse direction
    #
    # Returns false if the movement is allowable in the
    # current direction
    # 
    # Aborts if the movement is not possible in either direction

    if ( ( (current + (distance * direction)) < max ) and 
         ( (current + (distance * direction)) > min ) ):
        # Movement in the current direction is within safe limits,
        return False

    elif ( ( (current + (distance * direction)) >= max ) and 
           ( (current - (distance * direction)) >  min ) ):
        # Movement in the current direction violates maximum safe
        # value, but would be safe if the direction is reversed
        return True

    elif ( ( (current + (distance * direction)) <= min ) and 
           ( (current - (distance * direction)) <  max ) ):
        # Movement in the current direction violates minimum safe
        # value, but would be safe if the direction is reversed
        return True

    else:
        # Movement in *either* direction violates the safe working
        # envelope, so abort.
        # 
        print("\n*** ERROR ***")
        print("The current movement cannot be completed within the safe working envelope of")
        print("your machine. Turn on the --verbose option to see which MIDI data caused the")
        print("problem and adjust the MIDI file (or your safety limits if you are confident")
        print("you can do that safely). Aborting.")
        exit(2);
    
######################################
# Start of command line parsing code #
######################################

parser = argparse.ArgumentParser(description='Utility to process a Standard MIDI File (*.SMF/*.mid) to "play" it on up to 3 axes of a CNC machine.')

# Show the default values for each argument where available
#
parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter

input=parser.add_argument_group('Input settings')

input.add_argument(
    '-infile', '--infile',
    default = './midi_files/Super_Mario_Brothers_nodrums.mid',
    nargs   = '?',
    type    = argparse.FileType('r'),
    help    = 'the input MIDI filename'
)

input.add_argument(
    '-channels', '--channels',
    default = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    nargs   = '+',
    type    = int,
    choices = range(0,16),
    metavar = 'N',
    help    = 'list of MIDI channels you want to scan for event data'
)

input.add_argument(
    '-outfile', '--outfile',
    default = './gcode_files/output.gcode',
    nargs   = '?',
    type    = argparse.FileType('w'),
    help    = 'the output Gcode filename'
)

machines = parser.add_argument_group('Machine settings')

machines.add_argument(
    '-machine', '--machine',
    default = 'multicam_custom',
    choices = sorted(machines_dict),
    help    = 'sets everything up appropriately for predefined machines, or flags use of custom settings.'
)

custom = parser.add_argument_group('Customised settings')

custom.add_argument(
    '-units', '--units',
    default = 'metric',
    choices = sorted(units_dict),
    help    = 'set the measurement and feed rate units to your preferred scheme.'
)

custom.add_argument(
    '-ppu', '--ppu',
    metavar = ('XXX.XX', 'YYY.YY', 'ZZZ.ZZ'),
    nargs   = 3,
    type    = float,
    help    = 'set arbitrary pulses-per-unit (ppu) for each of the X, Y and Z axes'
)

custom.add_argument(
    '-safemin', '--safemin',
    metavar = ('XXX.XX', 'YYY.YY', 'ZZZ.ZZ'),
    nargs   = 3,
    type    = float,
    help    = 'set minimum edge of the safe envelope for each of the X, Y and Z axes'
)

custom.add_argument(
    '-safemax', '--safemax',
    metavar = ('XXX.XX', 'YYY.YY', 'ZZZ.ZZ'),
    nargs   = 3,
    type    = float,
    help    = 'set maximum edge of the safe envelope for each of the X, Y and Z axes'
)

custom.add_argument(
    '-prefix', '--prefix',
    metavar = 'PRE_FILE',
    nargs   = '?',
    type    = argparse.FileType('r'),
    help    = 'A file containing Gcode to set your machine to a known state before the MIDI is played e.g. homing the axes if supported or required.'
)

custom.add_argument(
    '-postfix', '--postfix',
    metavar = 'POST_FILE',
    nargs   = '?',
    type    = argparse.FileType('r'),
    help    = 'A file containing Gcode to return your machine to a known state after the MIDI is played e.g. homing the axes if supported or required.'
)

output=parser.add_argument_group('Output settings')

output.add_argument(
    '-axes', '--axes',
    default = 'XYZ',
    choices = sorted(axes_dict),
    metavar = 'XYZ',
    help    = 'ordered list of the axes you wish to "play" the MIDI data on. e.g. "X", "ZY", "YZX"'
)

output.add_argument(
    '-feedrate', '--feedrate',
    metavar = ('Nx', 'Ny', 'Nz'),
    default = 'seconds',
    choices = sorted(rate_dict),
    help    = "Set weather to output feedrate in unit pr second or unit pr minute"
)

output.add_argument(
    '-transpose', '--transpose',
    metavar = ('Nx', 'Ny', 'Nz'),
    default = ('0', '0', '0'),
    nargs   = 3,
    type    = float,
    help    = 'Transpose each axis N notes up/down, e.g. "12 0 0" will transpose the X axis one octave up the scale.'
)


output.add_argument(
    '-verbose', '--verbose',
    default = False,
    action  = 'store_true',
    help    = 'print verbose output to the terminal')

args = parser.parse_args()

# Get the chosen measurement scheme and the machine definition from the
# dictionaries defined above
#
scheme   =    units_dict.get( args.units   )
feedrate   =   rate_dict.get( args.feedrate   )
settings = machines_dict.get( args.machine )
feedrate_factor = feedrate[2]

# Check defaults and scaling of inputs
#
if args.ppu == None:
    # No manual setting of the axis scaling
    # 'scheme':'units', 'abbreviation', scale_to_mm]
    args.ppu    = [ 0, 0, 0 ]
    args.ppu[0] = ( settings[1] * scheme[2] )
    args.ppu[1] = ( settings[2] * scheme[2] )
    args.ppu[2] = ( settings[3] * scheme[2] )

if args.safemin == None:
    # No manual setting of the minimum safe edges
    # 'machine':[units, xppu, yppu, zppu, xmin, ymin, zmin, xmax, ymax, zmax, axes]
    args.safemin    = [ 0, 0, 0 ]
    args.safemin[0] = ( settings[4] / scheme[2] )
    args.safemin[1] = ( settings[5] / scheme[2] )
    args.safemin[2] = ( settings[6] / scheme[2] )

if args.safemax == None:
    # No manual setting of the maximum safe edges
    args.safemax    = [ 0, 0, 0 ]
    args.safemax[0] = ( settings[7] / scheme[2] )
    args.safemax[1] = ( settings[8] / scheme[2] )
    args.safemax[2] = ( settings[9] / scheme[2] )

if os.path.getsize(args.infile.name) == 0:
    msg="Input file %s is empty! Aborting." % os.path.basename(args.infile.name)
    raise argparse.ArgumentTypeError(msg)

print("MIDI input file:\n    %s" % args.infile.name)
print("Gcode output file:\n     %s" % args.outfile.name)

# Default is Cupcake, so check the others first

if args.machine == 'shapercube':
    print("Machine type:\n    Shapercube")
elif args.machine == 'ultimaker':
    print("Machine type:\n    Ultimaker")
elif args.machine == 'thingomatic':
    print("Machine type:\n    Makerbot Thing-O-Matic")
elif args.machine == 'custom':
    print("Machine type:\n    Bespoke machine")
elif args.machine == 'cupcake':
    print("Machine type:\n    Makerbot Cupcake CNC")

if args.axes != 'XYZ':
   active_axes = len(args.axes)

# Default is metric, so check the non-default case first
print("Units and Feed rates:\n    %s and %s/minute" % ( scheme[0], scheme[1] ))
print("Minimum safe limits [X, Y, Z]:\n    [%.3f, %.3f, %.3f]" % (args.safemin[0], args.safemin[1], args.safemin[2]))
print("Maximum safe limits [X, Y, Z]:\n    [%.3f, %.3f, %.3f]" % (args.safemax[0], args.safemax[1], args.safemax[2]))

print("Pulses per %s [X, Y, Z] axis:\n    [%.3f, %.3f, %.3f]" % (scheme[0], args.ppu[0], args.ppu[1], args.ppu[2]))

if active_axes > 1:
    print("Generate Gcode for:\n    %d axes in the order %s" % (active_axes, args.axes))
else:
    print("Generate Gcode for:\n    %s axis only" % args.axes)

# Set up an array to allow processing inside the loop to take account of the
# difference in feed rates required on each axis

suppress_comments = 0 # Set to 1 if your machine controller does not handle ( comments )

tempo=None # should be set by your MIDI...

def main(argv):
    x=0.0
    y=0.0
    z=0.0

    x_dir=1.0;
    y_dir=1.0;
    z_dir=1.0;

    #midi = midiparser.File(args.infile.name)
    midi = mido.MidiFile(args.infile.name)
    midi.debug = True

    print("\nMIDI file:\n    %s" % os.path.basename(args.infile.name))
    print("MIDI charset:\n    %s" % midi.charset)
    print("Number of tracks:\n    %d" % len(midi.tracks))
    print("Timing division:\n    %d" % midi.ticks_per_beat)

    noteEventList=[]
    all_channels=set()
    track_num = 0

    for track in midi.tracks:
        track: mido.MidiTrack
        absolute_time = 0
        channels=set()
        for event in track:
            event: mido.Message
            #Events return delta-time apparantly (Time since last event)
            #Adding these should give absolute times
            absolute_time += event.time
            if event is mido.messages.BaseMessage:
                print("Basemessage")
            if event is mido.Message:
                print("Message")
            if event is mido.MetaMessage:
                print("MetaMessage")
            if event is mido.UnknownMetaMessage:
                print("UnknownMetaMessage")
            if event.is_meta and event.type == "set_tempo":
                tempo=event.tempo
                if args.verbose:
                    print("Tempo change: " + str(tempo))
            if event.is_meta and event.type == "time_signature":
                if args.verbose:
                    print(f"Time Signature: {event.numerator}/{event.denominator}")
                    print(f"Notated 32nd notes pr. beat: {event.notated_32nd_notes_per_beat}")
                    print(f"Clocks pr. click: {event.clocks_per_click}")
            if event.is_meta and event.type == "key_signature":
                if args.verbose:
                    print(f"Key Signature: {event.key}")
            if ((event.type == "control_change") and (event.channel in args.channels)):
                if event.control >= 32 and \
                     event.control <= 63: pass # ===[ LSB Controller for 0-31 ]===
                                               # Same as 0 to 32 below, but value is little-endian, not big as usual
                elif event.control == 0: pass  # ===[ Bank Select ]===
                                               # Allows user to switch bank for patch selection.
                                               # Program change used with Bank Select.
                                               # MIDI can access 16,384 patches per MIDI channel.
                elif event.control == 1: pass  # ===[ Modulation Wheel ]===
                                               # Generally this CC controls a vibrato
                                               # effect (pitch, loudness, brighness).
                                               # What is modulated is based on the patch.
                elif event.control == 2: pass  # ===[ Breath Controller ]===
                                               # Oftentimes associated with aftertouch 
                                               # messages. It was originally intended for use with a breath
                                               # MIDI controller in which blowing harder produced higher MIDI
                                               # control values. It can be used for modulation as well.
                elif event.control == 3: pass  # !=== Undefined ===!
                elif event.control == 4: pass  # ===[ Foot Pedal ]===
                                               # Often used with aftertouch messages.
                                               # It can send a continuous stream of values based on how the pedal is used.
                elif event.control == 5: pass  # ===[ Portamento Time ]===
                                               # Controls portamento rate to slide
                                               # between 2 notes played subsequently.
                elif event.control == 6: pass  # ===[ Data Entry ]===
                                               # Controls Value for NRPN or RPN parameters.
                elif event.control == 7: pass  # ===[ Volume ]===
                                               # Controls the volume of the channel.
                elif event.control == 8: pass  # ===[ Balance ]===
                                               # Controls the left and right balance, generally
                                               # for _stereo_ patches. A value of 64 equals the center.
                elif event.control == 9: pass  # !=== Undefined ===!
                elif event.control == 10: pass # ===[ Pan ]===
                                               # Controls the left and right balance, generally
                                               # for _mono_ patches. A value of 64 equals the center.
                elif event.control == 11: pass # ===[ Expression ]===
                                               # Expression is a percentage of volume (CC7).
                elif event.control == 12: pass # ===[ Effect Controller 1 ]===
                                               # Usually used to control a parameter of an effect within
                                               # the synth or workstation.
                elif event.control == 13: pass # ===[ Effect Controller 2 ]===
                                               # Usually used to control a parameter of an effect within
                                               # the synth or workstation.

                # 14-15 undefined, 15-19 General purpose, 20-31 undefined

                elif event.control == 64: pass # ===[ Damper/sustain Pedal on/off ]===
                                               # Value of ≤63 is off, and ≥64 is on
                                               # On/off switch that controls sustain pedal. Nearly
                                               # every synth will react to CC 64. (See also Sostenuto CC 66)
                elif event.control == 65: pass # ===[ Portamento on/off ]===
                                               # On/off switch (Value of ≤63 is off, and ≥64 is on)
                                               # Portamento is a slide from one note to another,
                                               # especially in instruments such as the violin.
                elif event.control == 66: pass # ===[ Sostenuto Pedal on/off ]===
                                               # On/off switch – Like the Sustain controller (CC 64),
                                               # However, it only holds notes that were “On” when the
                                               # pedal was pressed. People use it to “hold” chords”
                                               # and play melodies over the held chord.
                elif event.control == 67: pass # ===[ Soft Pedal on/off ]===
                                               # On/off switch
                                               # Lowers the volume of notes played.
                elif event.control == 68: pass # ===[ Legato FootSwitch ]===
                                               # Turns Legato effect between 2 subsequent notes on or off.
                elif event.control == 69: pass # ===[ Hold 2 ]===
                                               # Another way to “hold notes” (see MIDI CC 64 and
                                               # MIDI CC 66). However notes fade out according to their
                                               # release parameter rather than when the pedal is released.
                elif event.control == 70: pass # ===[ Sound Controller 1 ]===
                                               # Usually controls the way a sound is produced.
                                               # Default = Sound Variation.
                elif event.control == 71: pass # ===[ Sound Controller 2 ]===
                                               # Allows shaping the Voltage Controlled Filter (VCF).
                                               # Default = Resonance also (Timbre or Harmonics)
                elif event.control == 72: pass # ===[ Sound Controller 3 ]===
                                               # Controls release time of the Voltage controlled
                                               # Amplifier (VCA). Default = Release Time.
                elif event.control == 73: pass # ===[ Sound Controller 4 ]===
                                               # Controls the “Attack’ of a sound. The attack is
                                               # the amount of time it takes for the sound to reach maximum amplitude.
                elif event.control == 74: pass # ===[ Sound Controller 5 ]===
                                               # Controls VCFs cutoff frequency of the filter.
                elif event.control >= 75 and \
                     event.control <= 79: pass # ===[ Sound Controller 6 to 10 ]===
                                               # Generic – Some manufacturers may use to further shave their sounds.

                # 80-83 Is generic controls

                elif event.control == 84: pass # ===[ Portamento CC Control ]===
                                               # Controls the amount of Portamento.
                # 85-90 undefined

                elif event.control == 91: pass # ===[ Effects Depth: Reverb ]===
                                               # Usually controls reverb send amount
                elif event.control == 92: pass # ===[ Effects Depth: Tremolo ]===
                                               # Usually controls tremolo amount
                elif event.control == 93: pass # ===[ Effects Depth: Chorus ]===
                                               # Usually controls chorus amount
                elif event.control == 94: pass # ===[ Effects Depth: Celeste (Detune) ]===
                                               # Usually controls detune amount
                elif event.control == 95: pass # ===[ Effects Depth: Phaser ]===
                                               # Usually controls phaser amount

                # 96-101 Non defined parameter adjustments
                # 102-119 undefined

                # 120-127 is channel "mode" messages. No values are used except for CC 122 and 126
                elif event.control == 120: pass # ===[ All Sound Off ]===
                                                # Mutes all sound. It does so regardless of release
                                                # time or sustain. (See MIDI CC 123)
                elif event.control == 121: pass # ===[ Reset All Controllers ]===
                                                # It will reset all controllers to their default.
                elif event.control == 122: pass # ===[ Local on/off Switch ]===
                                                # Turns internal connection of a MIDI keyboard or
                                                # workstation, etc. on or off. If you use a computer, you
                                                # will most likely want local control off to avoid notes
                                                # being played twice. Once locally and twice when
                                                # the note is sent back from the computer to your keyboard.
                                                # 0 = off , 127 = on
                elif event.control == 123: pass # ===[ All Notes Off ]===
                                                # Mutes all sounding notes. Release time will still be
                                                # maintained, and notes held by sustain will not turn
                                                # off until sustain pedal is depressed.
                elif event.control == 124: pass # ===[ Omni Mode Off ]===
                                                # Sets to “Omni Off” mode.
                elif event.control == 125: pass # ===[ Omni Mode On ]===
                                                # Sets to “Omni On” mode.
                elif event.control == 126: pass # ===[ Mono Mode ]===
                                                # Sets device mode to Monophonic. The value equals the
                                                # number of channels, or 0 if the number of channels
                                                # equals the number of voices in the receiver.
                elif event.control == 127: pass # ===[ Poly Mode ]===
                                                # Sets device mode to Polyphonic.
                
            if ((event.type == "note_on") and (event.channel in args.channels)): # filter undesired instruments

                if event.channel not in channels:
                    channels.add(event.channel)

                # NB: looks like some use "note on (vel 0)" as equivalent to note off, so check for vel=0 here and treat it as a note-off.
                # Comment: note_on (vel 0) is indeed used as note_off, but it is to keep the status flag set to running, thus
                # making the MIDI communication more efficient

                if event.velocity > 0:
                    noteEventList.append([absolute_time, 1, event.note, event.velocity])
                    if args.verbose:
                        print("Note on  (time, channel, note, velocity) : %6i %6i %6i %6i" % (absolute_time, event.channel, event.note, event.velocity) )
                else:
                    noteEventList.append([absolute_time, 0, event.note, event.velocity])
                    if args.verbose:
                        print("Note off (time, channel, note, velocity) : %6i %6i %6i %6i" % (absolute_time, event.channel, event.note, event.velocity) )
            if (event.type == "note_off") and (event.channel in args.channels):

                if event.channel not in channels:
                    channels.add(event.channel)

                noteEventList.append([absolute_time, 0, event.note, event.velocity])
                if args.verbose:
                    print("Note off (time, channel, note, velocity) : %6i %6i %6i %6i" % (absolute_time, event.channel, event.note, event.velocity) )

        # Finished with this track
        if len(channels) > 0:
            msg=', ' . join(['%2d' % ch for ch in sorted(channels)])
            print('Processed track %d, containing channels numbered: [%s ]' % (track_num, msg))
            all_channels = all_channels.union(channels)
        track_num += 1

    # List all channels encountered
    if len(all_channels) > 0:
        msg=', ' . join(['%2d' % ch for ch in sorted(all_channels)])
        print('The file as a whole contains channels numbered: [%s ]' % msg)

    # We now have entire file's notes with abs time from all channels
    # We don't care which channel/voice is which, but we do care about having all the notes in order
    # so sort event list by abstime to dechannelify

    noteEventList.sort()
    # print noteEventList
    # print len(noteEventList)

    last_time=-0
    active_notes={} # make this a dict so we can add and remove notes by name

    # Start the output to file...
    # It would be nice to add some metadata here, such as who/what generated the output, what the input file was,
    # and important playback parameters (such as steps/in assumed and machine envelope).
    # Unfortunately G-code comments are not 100% standardized...

    if suppress_comments == 0:
        args.outfile.write ("( Input file was " + os.path.basename(args.infile.name) + " )\n")
        
    # Code for everyone
    if args.units == 'imperial':
        args.outfile.write ("G20 (Imperial Hegemony Forevah!)\n")
    elif args.units == 'metric':
        args.outfile.write ("G21 (Metric FTW)\n")
    else:
        print("\nWARNING: Gcode metric/imperial setting undefined!\n")

    args.outfile.write ("G90 (Absolute posiitioning)\n")
    args.outfile.write ("G92 X0 Y0 Z0 (set origin to current position)\n")
    args.outfile.write ("G94 (set feed to mm/min)\n")
    args.outfile.write ("G0 X0 Y0 Z0 F2000.0 (Pointless move to origin to reset feed rate to a sane value)\n")

    # Handle the prefix Gcode, if present
    if args.prefix != None:
        # Read file and dump to outfile
        for line in args.prefix:
            args.outfile.write (line) 

    for note in noteEventList:
        # note[abs-time, 1=on 0=off, note, velocity]
        # Issue that next is that the length of the note isn't calculated from ON to OFF,
        # just from last time any note went on/off happened.
        # The first note will not work, since it's duration here will be "time since zero-time"
        # Duration should always look ahead to the turn-off message for the note
        # A list of "ON" notes should be kept, and track/channel should determin what axis it should
        # be played on. If a channel/track has multiple notes, user should be able to set
        # the "critical" notes to be played.
        # After running trough the entire song, the axis should be evaluated for MIN and MAX feedrate
        # since VERY low feedrates might need an octave transposing up, likewise for very high transpose down.
        # Possible options are to input a range of feedrates that the axis "plays best", and the
        # program can try and transpose all axis up or down by just one semitone.
        # Any song will be "OK" if ALL axis are transposed semitonal, and still OK if just one axis is transposed
        # a full octave.
        if last_time < note[0]:
        
            freq_xyz=[0,0,0]
            feed_xyz=[0,0,0]
            distance_xyz=[0,0,0]
            duration=0.0

            # "i" ranges from 0 to "the number of active notes *or* the number of active axes, 
            # whichever is LOWER". Note that the range operator stops
            # short of the maximum, so this means 0 to 2 at most for a 3-axis machine.
            # E.g. only look for the first few active notes to play despite what
            # is going on in the actual score.

            for i in range(0, min(len(active_notes.values()), active_axes)): 

                # Which axis are should we be writing to?
                # 
                j = axes_dict.get(args.axes)[i]

                # Debug
                # print"Axes %s: item %d is %d" % (axes_dict.get(args.axes), i, j)

                # Sound higher pitched notes first by sorting by pitch then indexing by axis
                #
                nownote=sorted(active_notes.values(), reverse=True)[i]

                # MIDI note 69     = A4(440Hz)
                # 2 to the power (69-69) / 12 * 440 = A4 440Hz
                # 2 to the power (64-69) / 12 * 440 = E4 329.627Hz
                #
                freq_xyz[j] = pow(2.0, (nownote-69 + int(args.transpose[j]))/12.0)*440.0

                # Here is where we need smart per-axis feed conversions
                # to enable use of X/Y *and* Z on a Makerbot
                #
                # feed_xyz[0] = X; feed_xyz[1] = Y; feed_xyz[2] = Z;
                #
                # Feed rate is expressed in feedrate_factor times
                # scaling factor is required.
                
                feed_xyz[j] = ( freq_xyz[j] * feedrate_factor ) / args.ppu[j]

                # Get the duration in seconds from the MIDI values in divisions, at the given tempo
                duration = mido.tick2second(note[0] - last_time, midi.ticks_per_beat, tempo)
                #duration = ( ( ( note[0] - last_time ) + 0.0 ) / ( midi.ticks_per_beat + 0.0 ) * ( tempo / 1000000.0 ) )

                # Get the actual relative distance travelled per axis in mm
                distance_xyz[j] = ( feed_xyz[j] * duration ) / feedrate_factor

            # Now that axes can be addressed in any order, need to make sure
            # that all of them are silent before declaring a rest is due.
            if distance_xyz[0] + distance_xyz[1] + distance_xyz[2] > 0.0: 
                # At least one axis is playing, so process the note into
                # movements
                #
                combined_feedrate = math.sqrt(feed_xyz[0]**2 + feed_xyz[1]**2 + feed_xyz[2]**2)
                
                if args.verbose:
                    print("Chord: [%7.3f, %7.3f, %7.3f] in Hz for %5.2f seconds at timestamp %i" % (freq_xyz[0], freq_xyz[1], freq_xyz[2], duration, note[0]))
                    print(" Feed: [%7.3f, %7.3f, %7.3f] XYZ %s/min and %8.2f combined" % (feed_xyz[0], feed_xyz[1], feed_xyz[2], scheme[1], combined_feedrate ))
                    print("Moves: [%7.3f, %7.3f, %7.3f] XYZ relative %s" % (distance_xyz[0], distance_xyz[1], distance_xyz[2], scheme[0] ))

                # Turn around BEFORE crossing the limits of the 
                # safe working envelope
                #
                if reached_limit( x, distance_xyz[0], x_dir, args.safemin[0], args.safemax[0] ):
                    x_dir = x_dir * -1
                x = (x + (distance_xyz[0] * x_dir))
               
                if reached_limit( y, distance_xyz[1], y_dir, args.safemin[1], args.safemax[1] ):
                    y_dir = y_dir * -1
                y = (y + (distance_xyz[1] * y_dir))
               
                if reached_limit( z, distance_xyz[2], z_dir, args.safemin[2], args.safemax[2] ):
                    z_dir = z_dir * -1
                z = (z + (distance_xyz[2] * z_dir))
               
                if args.verbose:
                    print("G01 X%.10f Y%.10f Z%.10f F%.10f\n" % (x, y, z, combined_feedrate))
                args.outfile.write("G01 X%.10f Y%.10f Z%.10f F%.10f\n" % (x, y, z, combined_feedrate))

            else:
                if duration > 0:
                    # This will never happen.
                    # When all distance_xyz are set to zero, the duration will also be zero
                    # But the above else statement will trigger when all notes go off.
                    # 
                    # Pauses need to be handeled differently.
                    # A solution would be to get the most quiet and most sensitive axis
                    # and set it to the lowest feedrate possible for that machine
                    # and let it travel a distance that results in the "pause" time being satisfied
                    # with a very quiet movement of the most silent axis.

                    # Handle 'rests' in addition to notes.
                    # How standard is this pause gcode, anyway?
                    args.outfile.write("G04 P%0.4f\n" % duration )
                    if args.verbose:
                        print("Pause for %.2f seconds" % duration)
                        print("G04 P%0.4f\n" % duration)

            # finally, set this absolute time as the new starting time
            last_time = note[0]

        if note[1]==1: # Note on
            if note[2] in active_notes:
                if args.verbose:
                    print("Warning: tried to turn on note already on!")
            else:
                # key and value are the same, but we don't really care.
                active_notes[note[2]]=note[2]
        elif note[1]==0: # Note off
            if note[2] in active_notes:
                active_notes.pop(note[2])
            else:
                if args.verbose:
                    print("Warning: tried to turn off note that wasn't on!")

    # Handle the postfix Gcode, if present
    if args.postfix != None:
        # Read file and dump to outfile
        for line in args.postfix:
            args.outfile.write (line) 
    
if __name__ == "__main__":
    main(sys.argv)
