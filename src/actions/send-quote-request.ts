
'use server';

import { Resend } from 'resend';
import { QuoteRequestEmail } from '@/emails/quote-request-email';
import * as z from 'zod';

const resend = new Resend(process.env.RESEND_API_KEY);

const formSchema = z.object({
  schoolName: z.string(),
  role: z.string(),
  schoolAddress: z.string(),
  schoolEmail: z.string().email(),
});

type FormData = z.infer<typeof formSchema>;

export async function sendQuoteRequest(data: FormData) {
  const toEmail = process.env.TO_EMAIL_ADDRESS;
  const fromEmail = process.env.FROM_EMAIL_ADDRESS;

  if (!toEmail || !fromEmail) {
    console.error('Missing TO_EMAIL_ADDRESS or FROM_EMAIL_ADDRESS in .env');
    return { error: 'Server configuration error. Please contact support.' };
  }

  try {
    const { data: result, error } = await resend.emails.send({
      from: `NestEdge Quote Request <${fromEmail}>`,
      to: [toEmail],
      subject: `New Quote Request from ${data.schoolName}`,
      react: QuoteRequestEmail(data),
    });

    if (error) {
      console.error('Resend error:', error);
      return { error: 'Failed to send email. Please try again.' };
    }

    return { success: true, data: result };
  } catch (exception) {
    console.error('Exception sending email:', exception);
    return { error: 'An unexpected error occurred. Please try again.' };
  }
}
