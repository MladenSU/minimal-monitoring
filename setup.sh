#!/bin/bash

SCRIPT_NAME=monitoring.py
FOLDER_NAME=minimal-monitoring
NON_ROOT_FULL_PATH="${HOME}/${FOLDER_NAME}"

if [[ $(id -u) -ne 0 ]]; then
    echo "We detected that the script is executed with a non-root user, which is not recommended."
    echo "If you proceed the tool will be configured for your current user."
    read -r -p "Would you like to proceed? y/n: " response
fi

if [[ $response == "y" ]]; then
    echo "Changing the location of the log file to - ${NON_ROOT_FULL_PATH}/minimal_monitoring.log"
    sed -i "s#/var/log#${NON_ROOT_FULL_PATH}#g" settings.ini

    echo "Adjusting the service file"
    sed -i "s#PATH#${NON_ROOT_FULL_PATH}/${SCRIPT_NAME}#g; s#USER#${USER}#g" minimal-monitoring.service

    echo "!NOTE THAT A SERVICE CANNOT BE CREATED, HENCE YOU SHOULD MANUALLY RUN THE SCRIPT!"
    exit 0
fi

mkdir -p /etc/minimal-monitoring && mv settings.ini /etc/minimal-monitoring

touch /var/log/minimal_monitoring.log &&
    echo "Successfully create the log file!" ||
    { echo "Failed to create the log file!" && exit 1; }

mv monitoring.py /usr/bin/ &&
    echo "Successfully move the script under /usr/bin" ||
    { "Failed to move the script" && exit 1; }

grep -qE "/usr/bin" <<<"${PATH}" ||
    echo "/usr/bin is NOT in your $PATH variable, please fix."

sed -i "s#PATH#/usr/bin/${SCRIPT_NAME}#g; s#USER#${USER}#g" minimal-monitoring.service

cp minimal-monitoring.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable minimal-monitoring.service
systemctl start minimal-monitoring.service
systemctl status minimal-monitoring.service