import { Mail, Phone, MapPin } from 'lucide-react';
import { ContactForm } from '@/components/contact/ContactForm';
import Chatbot from '@/components/contact/Chatbot';
import OfficeMap from '@/components/contact/OfficeMap';

export default function ContactPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold">Get in Touch</h1>
          <p className="mt-4 text-lg text-primary-foreground/80 max-w-3xl mx-auto">
            We're here to help. Whether you have a question about features, trials, or anything else, our team is ready to answer all your questions.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
            <div className="lg:col-span-1 space-y-8">
              <h2 className="font-headline text-3xl font-bold">Contact Information</h2>
              <div className="space-y-4 text-muted-foreground">
                <div className="flex items-center gap-4">
                  <Mail className="w-6 h-6 text-primary" />
                  <a href="mailto:sales@nestedge.com" className="hover:text-primary">sales@nestedge.com</a>
                </div>
                <div className="flex items-center gap-4">
                  <Phone className="w-6 h-6 text-primary" />
                  <span>(123) 456-7890</span>
                </div>
                <div className="flex items-start gap-4">
                  <MapPin className="w-6 h-6 text-primary mt-1" />
                  <span>123 Innovation Drive, Tech City, 12345</span>
                </div>
              </div>
               <div className="mt-8 rounded-lg overflow-hidden shadow-lg">
                <OfficeMap />
              </div>
            </div>
            
            <div className="lg:col-span-2 space-y-12">
              <div>
                <h2 className="font-headline text-3xl font-bold mb-6">Send us a Message</h2>
                <ContactForm />
              </div>
              <div>
                <h2 className="font-headline text-3xl font-bold mb-6">Ask our AI Assistant</h2>
                <Chatbot />
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
