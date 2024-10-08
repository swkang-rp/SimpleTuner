import torch
import random
from helpers.models.flux.pipeline import FluxPipeline
from helpers.training import steps_remaining_in_epoch


def get_mobius_guidance(args, global_step, steps_per_epoch, batch_size, device):
    """
    state of the art
    """
    steps_remaining = steps_remaining_in_epoch(global_step, steps_per_epoch)

    # Start with a linear mapping from remaining steps to a scale between 0 and 1
    scale_factor = steps_remaining / steps_per_epoch

    # we want the last 10% of the epoch to have a guidance of 1.0
    threshold_step_count = max(1, int(steps_per_epoch * 0.1))

    if (
        steps_remaining <= threshold_step_count
    ):  # Last few steps in the epoch, set guidance to 1.0
        guidance_values = [1.0 for _ in range(batch_size)]
    else:
        # Sample between flux_guidance_min and flux_guidance_max with bias towards 1.0
        guidance_values = [
            random.uniform(args.flux_guidance_min, args.flux_guidance_max)
            * scale_factor
            + (1.0 - scale_factor)
            for _ in range(batch_size)
        ]

    return guidance_values


def update_flux_schedule_to_fast(args, noise_scheduler_to_copy):
    if args.flux_fast_schedule and args.flux:
        # 4-step noise schedule [0.7, 0.1, 0.1, 0.1] from SD3-Turbo paper
        for i in range(0, 250):
            noise_scheduler_to_copy.sigmas[i] = 1.0
        for i in range(250, 500):
            noise_scheduler_to_copy.sigmas[i] = 0.3
        for i in range(500, 750):
            noise_scheduler_to_copy.sigmas[i] = 0.2
        for i in range(750, 1000):
            noise_scheduler_to_copy.sigmas[i] = 0.1
    return noise_scheduler_to_copy


def pack_latents(latents, batch_size, num_channels_latents, height, width):
    latents = latents.view(
        batch_size, num_channels_latents, height // 2, 2, width // 2, 2
    )
    latents = latents.permute(0, 2, 4, 1, 3, 5)
    latents = latents.reshape(
        batch_size, (height // 2) * (width // 2), num_channels_latents * 4
    )

    return latents


def unpack_latents(latents, height, width, vae_scale_factor):
    batch_size, num_patches, channels = latents.shape

    height = height // vae_scale_factor
    width = width // vae_scale_factor

    latents = latents.view(batch_size, height, width, channels // 4, 2, 2)
    latents = latents.permute(0, 3, 1, 4, 2, 5)

    latents = latents.reshape(batch_size, channels // (2 * 2), height * 2, width * 2)

    return latents


def prepare_latent_image_ids(batch_size, height, width, device, dtype):
    latent_image_ids = torch.zeros(height // 2, width // 2, 3)
    latent_image_ids[..., 1] = (
        latent_image_ids[..., 1] + torch.arange(height // 2)[:, None]
    )
    latent_image_ids[..., 2] = (
        latent_image_ids[..., 2] + torch.arange(width // 2)[None, :]
    )

    latent_image_id_height, latent_image_id_width, latent_image_id_channels = (
        latent_image_ids.shape
    )

    latent_image_ids = latent_image_ids[None, :].repeat(batch_size, 1, 1, 1)
    latent_image_ids = latent_image_ids.reshape(
        batch_size,
        latent_image_id_height * latent_image_id_width,
        latent_image_id_channels,
    )

    return latent_image_ids.to(device=device, dtype=dtype)
