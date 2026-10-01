import { z } from "zod";

export const SessionUserSchema = z.object({
  subject: z.string().min(1),
  email: z.email(),
  display_name: z.string().min(1),
  tenant_id: z.string().min(1),
  rep_id: z.string().min(1),
  roles: z.array(z.string()),
});

export const BackendTokenSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer").default("bearer"),
  expires_at: z.iso.datetime(),
  absolute_expires_at: z.iso.datetime(),
  user: SessionUserSchema,
});

export const BackendSessionSchema = z.object({ user: SessionUserSchema });

export type SessionUser = z.infer<typeof SessionUserSchema>;
