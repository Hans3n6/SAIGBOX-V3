# AWS Bedrock Setup for SAIG

## Prerequisites
You need an AWS account with access to Amazon Bedrock and the Claude 3 Sonnet model.

## Step 1: Enable Bedrock Model Access

1. Go to AWS Console: https://console.aws.amazon.com/
2. Navigate to Amazon Bedrock service
3. Go to "Model access" in the left menu
4. Request access to "Claude 3 Sonnet" (anthropic.claude-3-sonnet-20240229-v1:0)
5. Wait for approval (usually instant for Claude models)

## Step 2: Create IAM User and Get Credentials

1. Go to IAM service in AWS Console
2. Click "Users" → "Create user"
3. Name: `saigbox-bedrock-user`
4. Click "Next"
5. Select "Attach policies directly"
6. Search for and select: `AmazonBedrockFullAccess`
7. Click "Next" → "Create user"
8. Click on the created user
9. Go to "Security credentials" tab
10. Click "Create access key"
11. Select "Application running outside AWS"
12. Click "Next" → "Create access key"
13. **IMPORTANT**: Copy the Access key ID and Secret access key

## Step 3: Update .env File

Replace the placeholder values in your `.env` file:

```
AWS_ACCESS_KEY_ID=<your-access-key-id>
AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
AWS_REGION=us-east-1
```

## Step 4: Restart the Server

After updating the .env file, restart the server for changes to take effect.

## Troubleshooting

If you get "UnrecognizedClientException" error:
- Verify your AWS credentials are correct
- Ensure the IAM user has Bedrock permissions
- Check that Claude 3 Sonnet model access is enabled in your region

If you get "Model not found" error:
- Make sure you're using the correct region (us-east-1 recommended)
- Verify Claude 3 Sonnet is available in your region