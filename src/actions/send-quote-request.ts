'use server';

import { Resend } from 'resend';
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
      from: fromEmail,
      to: [toEmail],
      subject: `New Quote Request from ${data.schoolName}`,
      text: `
        A new quote request has been submitted.
        
        School Name: ${data.schoolName}
        Role: ${data.role}
        School Address: ${data.schoolAddress}
        School Email: ${data.schoolEmail}
      `,
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
