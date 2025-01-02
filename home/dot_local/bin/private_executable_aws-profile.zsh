#!/bin/zsh

# Function to list AWS profiles inside the config file
list_aws_profiles() {
    sed -nE 's/^\[profile (.*)\]/\1/p' ~/.aws/config
}

# Function to display the current AWS_PROFILE
display_aws_profile() {
    echo "AWS profile set to '$AWS_PROFILE'"
}

# Function to select a profile
select_aws_profile() {
    local profiles=( "${(@f)$(list_aws_profiles)}" )
    echo "Available AWS profiles:"
    for i in {1..$#profiles}; do
	if [[ "$AWS_PROFILE" == "$profiles[$i]" ]]; then
            printf "%3d) *%s\n" $i $profiles[$i]
        else
            printf "%3d) %s\n" $i $profiles[$i]
        fi
    done
    while true; do
        echo -n "Select an AWS profile (1-${#profiles[@]}): "
        read -r choice
        if [[ $choice =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= $#profiles )); then
            export AWS_PROFILE=$profiles[$choice]
            echo "AWS profile set to '$AWS_PROFILE'"
            break
        else
            echo "Invalid selection. Please try again."
        fi
    done
}

# Function to set AWS_PROFILE
set_aws_profile() {
    local profile_name="$1"
    if grep -qE "^\[profile $profile_name\]" ~/.aws/config; then
        export AWS_PROFILE="$profile_name"
        echo "AWS profile set to '$AWS_PROFILE'"
    else
        echo "Error: Profile '$profile_name' does not exist in ~/.aws/config"
    fi
}

case "$1" in
    --display|-d)
        display_aws_profile
        ;;
    --list|-l)
	list_aws_profiles
	;;
    --set|-s)
        if [ -n "$2" ]; then
            set_aws_profile "$2"
        else
            echo "Error: No profile name provided"
        fi
        ;;
    *)
	select_aws_profile
        ;;
esac

