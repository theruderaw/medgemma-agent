import Markdown from './Markdown';
import { StreamCaret } from '../ui/StreamIndicators';

interface Props {
    text: string;
    streaming?: boolean;
}

export default function MessageContent({ text, streaming }: Props) {
    if (streaming) {
        return (
            <span className="whitespace-pre-wrap">
                {text}
                <StreamCaret />
            </span>
        );
    }
    return <Markdown text={text} />;
}
