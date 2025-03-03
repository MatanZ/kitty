#!/bin/zsh

() {
    if [[ ! -o interactive ]]; then return; fi
    if [[ -z "$KITTY_SHELL_INTEGRATION" ]]; then return; fi
    if [[ ! -z "$_ksi_prompt" ]]; then return; fi
    typeset -g -A _ksi_prompt
    _ksi_prompt=(state first-run is_last_precmd y cursor y title y mark y complete y)
    for i in ${=KITTY_SHELL_INTEGRATION}; do
        if [[ "$i" == "no-cursor" ]]; then _ksi_prompt[cursor]='n'; fi
        if [[ "$i" == "no-title" ]]; then _ksi_prompt[title]='n'; fi
        if [[ "$i" == "no-prompt-mark" ]]; then _ksi_prompt[mark]='n'; fi
        if [[ "$i" == "no-complete" ]]; then _ksi_prompt[complete]='n'; fi
    done
    unset KITTY_SHELL_INTEGRATION

    function _ksi_debug_print() {
        # print a line to STDOUT of parent kitty process
        local b=$(printf "%s\n" "$1" | base64 | tr -d \\n)
        printf "\eP@kitty-print|%s\e\\" "$b"
    }

    function _ksi_change_cursor_shape () {
        # change cursor shape depending on mode
        if [[ "$_ksi_prompt[cursor]" == "y" ]]; then
            case $KEYMAP in
                vicmd | visual)
                    # the command mode for vi
                    printf "\e[1 q"  # blinking block cursor
                ;;
                *)
                    printf "\e[5 q"  # blinking bar cursor
                ;;
            esac
        fi
    }

    function _ksi_osc() {
        printf "\e]%s\a" "$1"
    }

    function _ksi_mark() {
        # tell kitty to mark the current cursor position using OSC 133
        if [[ "$_ksi_prompt[mark]" == "y" ]]; then _ksi_osc "133;$1"; fi
    }
    _ksi_prompt[start_mark]="%{$(_ksi_mark A)%}"
    _ksi_prompt[secondary_mark]="%{$(_ksi_mark 'A;k=s')%}"

    function _ksi_set_title() {
        if [[ "$_ksi_prompt[title]" == "y" ]]; then _ksi_osc "2;$1"; fi
    }

    function _ksi_install_completion() {
        if [[ "$_ksi_prompt[complete]" == "y" ]]; then
            # compdef is only defined if compinit has been called
            if whence compdef > /dev/null; then 
                compdef _ksi_complete kitty 
            fi
        fi
    }

    function _ksi_precmd() { 
        local cmd_status=$?
        # Set kitty window title to the cwd, appropriately shortened, see
        # https://unix.stackexchange.com/questions/273529/shorten-path-in-zsh-prompt
        _ksi_set_title $(print -P '%(4~|…/%3~|%~)')

        # Prompt marking
        if [[ "$_ksi_prompt[mark]" == "y" ]]; then
            if [[ "$_ksi_prompt[state]" == "preexec" ]]; then
                _ksi_mark "D;$cmd_status"
            else
                if [[ "$_ksi_prompt[state]" != "first-run" ]]; then _ksi_mark "D"; fi
            fi
            # we must use PS1 to set the prompt start mark as precmd functions are 
            # not called when the prompt is redrawn after a window resize or when a background
            # job finishes. However, if we are not the last function in precmd_functions which
            # can be the case on first run, PS1 might be broken by a following function, so
            # output the mark directly in that case
            if [[ "$_ksi_prompt[is_last_precmd]" != "y" ]]; then
                _ksi_mark "A";
                _ksi_prompt[is_last_precmd]="y";
            else
                if [[ "$PS1" != *"$_ksi_prompt[start_mark]"* ]]; then PS1="$_ksi_prompt[start_mark]$PS1" fi
            fi
            # PS2 is used for prompt continuation. On resize with a continued prompt only the last
            # prompt is redrawn so we need to mark it
            if [[ "$PS2" != *"$_ksi_prompt[secondary_mark]"* ]]; then PS2="$_ksi_prompt[secondary_mark]$PS2" fi
        fi
        _ksi_prompt[state]="precmd"
    }

    function _ksi_zle_line_init() { 
        if [[ "$_ksi_prompt[mark]" == "y" ]]; then _ksi_mark "B"; fi
        _ksi_change_cursor_shape
        _ksi_prompt[state]="line-init"
    }

    function _ksi_zle_line_finish() { 
        _ksi_change_cursor_shape
        _ksi_prompt[state]="line-finish"
    }

    function _ksi_preexec() { 
        if [[ "$_ksi_prompt[mark]" == "y" ]]; then 
            _ksi_mark "C"; 
            # remove the prompt mark sequence while the command is executing as it could read/modify the value of PS1
            PS1="${PS1//$_ksi_prompt[start_mark]/}"
            PS2="${PS2//$_ksi_prompt[secondary_mark]/}"
        fi
        # Set kitty window title to the currently executing command
        _ksi_set_title "$1"
        _ksi_prompt[state]="preexec"
    }

    function _ksi_first_run() {
        # We install the real precmd and preexec functions here and remove this function 
        # from precmd_functions. This ensures that our functions are last. This is needed
        # because the zsh prompt_init package actually sets PS1 in a precmd function and the user
        # could have setup their own precmd function to set the prompt as well.
        _ksi_install_completion
        typeset -a -g precmd_functions
        local idx=$precmd_functions[(ie)_ksi_first_run] 
        if [[ $idx -gt 0 ]]; then
            if [[ $idx -lt ${#precmd_functions[@]} ]]; then 
                _ksi_prompt[is_last_precmd]="n"
            fi
            add-zsh-hook -d precmd _ksi_first_run
            add-zsh-hook precmd _ksi_precmd
            add-zsh-hook preexec _ksi_preexec
            add-zle-hook-widget keymap-select _ksi_change_cursor_shape
            add-zle-hook-widget line-init _ksi_zle_line_init
            add-zle-hook-widget line-finish _ksi_zle_line_finish
            _ksi_precmd
        fi
    }

    # Completion for kitty
    _ksi_complete() {
        local src
        # Send all words up to the word the cursor is currently on
        src=$(printf "%s\n" "${(@)words[1,$CURRENT]}" | kitty +complete zsh "_matcher=$_matcher")
        if [[ $? == 0 ]]; then
            eval ${src}
        fi
    }

    autoload -Uz add-zsh-hook
    autoload -Uz add-zle-hook-widget
    add-zsh-hook precmd _ksi_first_run
}
