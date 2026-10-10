variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID; pass via TF_VAR_cloudflare_account_id."
}

variable "environment" {
  type        = string
  default     = "production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}
