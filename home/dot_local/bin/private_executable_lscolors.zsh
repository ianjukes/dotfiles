#!/bin/zsh

# Set the number of columns
columns=32

# Calculate the range of colors to display per column
colors_per_column=8

for color_code in {0..7}; do
  # Initialize an empty string for the line to be printed
  line=""

  for (( column=0; column<columns; column++ )); do
    # Calculate the color code for the current column
    current_color=$((color_code + (column * colors_per_column)))

    # Format the color code with leading zeros
    printf -v padded_current_color "%03d" $current_color

    # Append the formatted color code to the line string
    if (( column < columns - 1 )); then
      line+="%F{$current_color}$padded_current_color%F{reset} "
    else
      line+="%F{$current_color}$padded_current_color%F{reset}"
    fi
  done

  # Print the line
  print -P $line
done

