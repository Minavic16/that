
import {
  Body,
  Container,
  Head,
  Heading,
  Hr,
  Html,
  Preview,
  Section,
  Text,
} from '@react-email/components';
import * as React from 'react';

interface QuoteRequestEmailProps {
  schoolName: string;
  role: string;
  schoolAddress: string;
  schoolEmail: string;
}

export function QuoteRequestEmail({
  schoolName,
  role,
  schoolAddress,
  schoolEmail,
}: QuoteRequestEmailProps) {
  return (
    <Html>
      <Head />
      <Preview>New Quote Request from {schoolName}</Preview>
      <Body style={main}>
        <Container style={container}>
          <Heading style={heading}>New Quote Request for NestEdge</Heading>
          <Text style={paragraph}>
            A new quote request has been submitted through the website.
          </Text>
          <Section style={detailsSection}>
            <Text style={detailsTitle}>Requester Details:</Text>
            <Text style={detailsText}>
              <strong>School Name:</strong> {schoolName}
            </Text>
            <Text style={detailsText}>
              <strong>Role:</strong> {role}
            </Text>
            <Text style={detailsText}>
              <strong>School Address:</strong> {schoolAddress}
            </Text>
            <Text style={detailsText}>
              <strong>School Email:</strong> <a href={`mailto:${schoolEmail}`}>{schoolEmail}</a>
            </Text>
          </Section>
          <Hr style={hr} />
          <Text style={footer}>
            This email was generated automatically from the NestEdge website.
          </Text>
        </Container>
      </Body>
    </Html>
  );
}

// Styles
const main = {
  backgroundColor: '#f6f9fc',
  fontFamily:
    '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Ubuntu,sans-serif',
};

const container = {
  backgroundColor: '#ffffff',
  margin: '0 auto',
  padding: '20px 0 48px',
  marginBottom: '64px',
  border: '1px solid #e6ebf1',
  borderRadius: '5px',
};

const heading = {
  color: '#333',
  fontSize: '24px',
  fontWeight: 'bold',
  textAlign: 'center' as const,
  margin: '30px 0',
};

const paragraph = {
  color: '#555',
  fontSize: '16px',
  lineHeight: '26px',
  padding: '0 20px',
};

const detailsSection = {
  backgroundColor: '#fafafa',
  padding: '20px',
  margin: '20px',
  border: '1px solid #eaeaea',
  borderRadius: '5px',
};

const detailsTitle = {
  fontSize: '18px',
  fontWeight: 'bold',
  color: '#333',
  margin: '0 0 15px 0',
};

const detailsText = {
  fontSize: '14px',
  lineHeight: '22px',
  color: '#555',
  margin: '0 0 10px 0',
};

const hr = {
  borderColor: '#e6ebf1',
  margin: '20px 0',
};

const footer = {
  color: '#8898aa',
  fontSize: '12px',
  lineHeight: '16px',
  textAlign: 'center' as const,
};
