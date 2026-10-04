name                = "voice-platform-dev"
region              = "us-east-1"
availability_zones  = ["us-east-1a", "us-east-1b", "us-east-1c"]
deletion_protection = true
tags                = { Environment = "dev", ManagedBy = "terraform" }
