#!/usr/bin/env bash

MFA_ARN="arn:aws:iam::956723945403:mfa/Byeonghee-Lee"

echo -n "MFA Code: "
read TOKEN_CODE

CREDS=$(aws sts get-session-token \
    --profile Byeonghee-Lee \
    --serial-number "$MFA_ARN" \
    --token-code "$TOKEN_CODE" \
    --duration-seconds 43200)

if [ $? -ne 0 ]; then
    echo "MFA session update failed."
    exit 1
fi

aws configure set aws_access_key_id \
    "$(echo "$CREDS" | jq -r '.Credentials.AccessKeyId')" \
    --profile default

aws configure set aws_secret_access_key \
    "$(echo "$CREDS" | jq -r '.Credentials.SecretAccessKey')" \
    --profile default

aws configure set aws_session_token \
    "$(echo "$CREDS" | jq -r '.Credentials.SessionToken')" \
    --profile default

aws configure set aws_security_token \
    "$(echo "$CREDS" | jq -r '.Credentials.SessionToken')" \
    --profile default

echo "MFA session updated."

aws sts get-caller-identity