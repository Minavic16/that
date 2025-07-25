// This file is machine-generated - edit with care!

'use server';

/**
 * @fileOverview Implements a chatbot flow for the NestEdge website to answer user questions.
 *
 * - answerQuestion - A function that processes user questions and returns answers from the chatbot.
 * - AnswerQuestionInput - The input type for the answerQuestion function.
 * - AnswerQuestionOutput - The return type for the answerQuestion function.
 */

import {ai} from '@/ai/genkit';
import {z} from 'genkit';

const AnswerQuestionInputSchema = z.object({
  question: z.string().describe('The question asked by the user.'),
});

export type AnswerQuestionInput = z.infer<typeof AnswerQuestionInputSchema>;

const AnswerQuestionOutputSchema = z.object({
  answer: z.string().describe('The answer from the chatbot to the user question.'),
});

export type AnswerQuestionOutput = z.infer<typeof AnswerQuestionOutputSchema>;

export async function answerQuestion(input: AnswerQuestionInput): Promise<AnswerQuestionOutput> {
  return answerQuestionFlow(input);
}

const prompt = ai.definePrompt({
  name: 'aiChatbotPrompt',
  input: {schema: AnswerQuestionInputSchema},
  output: {schema: AnswerQuestionOutputSchema},
  prompt: `You are a chatbot designed to answer questions about NestEdge, a SaaS platform offering tools for school management and real estate operations.

NestEdge has two primary products:

1.  NestEdge School Management Engine: A powerful all-in-one tool for secondary school operations, including student registration, timetable management, result computation, and parent-teacher communication.
2.  NestEstate: An intuitive platform for real estate listing, management, and sales, offering features like property listings, agent dashboards, booking forms, and geo-location.

NestEdge is a subsidiary of GMG, an educational and innovation-focused organization.

Mission Statement: To build smart, scalable software solutions that simplify education and real estate systems for the modern world.
Vision Statement: To empower schools, agents, and communities through digital transformation.

Use the above information to answer the following question:

{{question}}`,
});

const answerQuestionFlow = ai.defineFlow(
  {
    name: 'answerQuestionFlow',
    inputSchema: AnswerQuestionInputSchema,
    outputSchema: AnswerQuestionOutputSchema,
  },
  async input => {
    const {output} = await prompt(input);
    return output!;
  }
);
