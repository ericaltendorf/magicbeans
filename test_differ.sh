#!/bin/bash

echo "input side a (one line)"
read a_content

echo "input side b (one line)"
read b_content

echo $a_content | sed -e 's/E *[+-]//' -e 's/ \(20..-..-\)/
echo $b_content | sed -e 's/E *[+-]//' -e 's/ \(20..-..-\)/

meld a b