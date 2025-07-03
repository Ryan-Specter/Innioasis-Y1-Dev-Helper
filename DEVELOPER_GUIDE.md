# Y1 Developer Guide: Building Apps for Non-Touch 480x360 Display

## Overview

The Innioasis Y1 is a unique Android-based digital audio player with specific hardware constraints that require special consideration when developing apps. This guide will help you create apps that work seamlessly with the Y1's limited input system and display.

## Hardware Specifications

### Display
- **Resolution**: 480x360 pixels
- **Type**: Non-touch LCD display
- **Aspect Ratio**: 4:3
- **Color Depth**: 16-bit (RGB565) or 24-bit (RGB888/RGBA8888)

### Input System
The Y1 has a limited set of physical inputs that must be mapped to Android keycodes:

#### Primary Navigation
- **D-pad Left**: `KEYCODE_DPAD_LEFT` (21)
- **D-pad Right**: `KEYCODE_DPAD_RIGHT` (22)
- **D-pad Up**: `KEYCODE_DPAD_UP` (19)
- **D-pad Down**: `KEYCODE_DPAD_DOWN` (20)
- **D-pad Center/Enter**: `KEYCODE_ENTER` (66) or `KEYCODE_DPAD_CENTER` (23)
- **Back Button**: `KEYCODE_BACK` (4)

#### Media Controls
- **Play/Pause**: `KEYCODE_MEDIA_PLAY_PAUSE` (85)
- **Previous Track**: `KEYCODE_MEDIA_PREVIOUS` (88)
- **Next Track**: `KEYCODE_MEDIA_NEXT` (87)

#### Long Press Support
- All buttons support long press for context menus
- Long press duration: 500ms (standard Android)

## Design Principles

### 1. One-Direction Navigation Flow
**Best Practice**: Design your app's navigation to flow primarily in one of two directions:
- **Vertical Flow**: Up/Down navigation (recommended for most apps)
- **Horizontal Flow**: Left/Right navigation (for side-scrolling content)

**Why This Matters**: The Y1 is an iPod-like device where vertical scrolling feels natural and intuitive. Most content (playlists, settings, file lists) works better with up/down navigation.

### 2. Essential Navigation Actions
Every app must support these core actions:
- **Selection**: `KEYCODE_ENTER` to select/confirm
- **Back Navigation**: `KEYCODE_BACK` to return to previous screen
- **Context Menus**: Long press for additional options

### 3. Screen Layout Guidelines
- **Target Size**: Minimum 48x48dp for selectable elements
- **Spacing**: Adequate spacing between interactive elements
- **Focus Indicators**: Clear visual feedback for selected items
- **Text Size**: Minimum 14sp for readability on 480x360 display

## Development Setup

### Prepare Device for Development
Before starting development, use the Y1 Helper's "Prepare Device" feature to install the stock Y1 launcher (version 2.1.9). This ensures:
- **Consistent Environment**: Proper launcher interface for testing
- **API Level 16**: Target Android 4.2.2 Jelly Bean
- **Real Hardware**: Development on actual Y1 device
- **Stock Interface**: Access to the intended Y1 user experience

### Target Specifications
- **Android Version**: 4.2.2 Jelly Bean (API Level 16)
- **Display**: 480x360 non-touch LCD
- **Input**: D-pad navigation + media buttons
- **Platform**: MediaTek MT6572 