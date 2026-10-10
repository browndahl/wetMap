locals {
  bucket_name = "wetmap-radar-${var.environment}"
}

resource "cloudflare_r2_bucket" "radar" {
  account_id    = var.cloudflare_account_id
  name          = local.bucket_name
  jurisdiction  = "eu"
  location      = "weur"
  storage_class = "Standard"
}

resource "cloudflare_r2_bucket_lifecycle" "radar" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.radar.name
  rules = [{
    id         = "delete-radar-frames-after-2-days"
    enabled    = true
    conditions = { prefix = "frames/" }
    delete_objects_transition = {
      condition = { max_age = 172800, type = "Age" }
    }
  }]
}

output "radar_bucket" { value = cloudflare_r2_bucket.radar.name }
